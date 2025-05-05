import os
import re
from collections import Counter
from pathlib import Path

from app import values, spectra, emitter, llm_integration
import javalang

from app.values import llm_prompt_example_3, llm_prompt_example_1, llm_prompt_template

def extract_oracle(spectra, top_n=10):
    # Read bug report
    if Path(values.file_bug_report).is_file():
        emitter.debug(f"Found bug report at: {values.file_bug_report}")
        with open(values.file_bug_report, 'r') as file:
            bug_report = file.read()
    else:
        emitter.error(f"Bug report file not found at expected location: {values.file_bug_report}")
        return

    # Get suspicious locations
    locations = spectra.get_top_suspicious_locations(top_n=top_n)
    num_locations = len(locations)
    emitter.information(f"Top {num_locations} suspicious locations:")
    for idx, loc in enumerate(locations, start=1):
        emitter.information(f"{idx}: {loc}")

    # Track how often each method is extracted and its weighted points
    method_counts = Counter()
    method_points = Counter()
    method_info = {}

    for idx, loc in enumerate(locations, start=1):
        # Assign weight dynamically based on number of locations
        weight = num_locations - idx + 1

        # Read in java file for this location, handling inner classes
        full_class = loc.class_name
        pkg, _, cls_inner = full_class.rpartition('.')
        outer_cls = cls_inner.split('$', 1)[0]
        dir_parts = pkg.split('.') if pkg else []
        target_file = Path(values.dir_info["source"], *dir_parts, outer_cls).with_suffix(".java")
        if not os.path.isfile(target_file):
            emitter.error(f"Source file not found for class {loc.class_name}: {target_file}")
            continue
        with open(target_file, 'r') as f:
            code_lines = f.readlines()
            code_text = ''.join(code_lines)

        # Extract method containing the suspicious line
        result = extract_method(loc, code_lines, code_text)
        if result is None:
            continue
        java_doc, method_name, method_code, m_start, m_end = result

        # Use method signature (first line) as key
        signature = method_code.strip().splitlines()[0].strip()
        method_counts[signature] += 1
        method_points[signature] += weight

        # Store info for this method if not already stored
        if signature not in method_info:
            method_info[signature] = {
                "java_doc": java_doc,
                "method_name": method_name,
                "method_code": method_code,
                "m_start": m_start,
                "m_end": m_end,
                "code_lines": code_lines
            }

    # Print summary of extracted methods
    emitter.information("Method extraction summary:")
    for signature, info in method_info.items():
        count = method_counts[signature]
        points = method_points[signature]
        emitter.information(f"Method {signature} extracted {count} times, total points {points}")

    # Select the method with highest points, handling ties
    if not method_points:
        emitter.error("No methods extracted from suspicious locations")
        return

    max_points = max(method_points.values())
    candidates = [sig for sig, pts in method_points.items() if pts == max_points]
    if len(candidates) > 1:
        emitter.warning(f"Tie detected between methods: {candidates}, choosing by occurrence counts")
        # Tie-break by highest extraction count, then by insertion order
        best_signature = max(
            candidates,
            key=lambda sig: (method_counts[sig], -list(method_info.keys()).index(sig))
        )
    else:
        best_signature = candidates[0]

    best_info = method_info[best_signature]
    java_doc = best_info["java_doc"]
    method_name = best_info["method_name"]
    method_code = best_info["method_code"]
    m_start = best_info["m_start"]
    m_end = best_info["m_end"]
    code_lines = best_info["code_lines"]

    emitter.information(f"Selected method: {best_signature} with {method_counts[best_signature]} occurrences and {method_points[best_signature]} points")

    # Write the selected method to extract.java
    with open(values.dir_output / "extract.java", "w", encoding="utf-8") as f:
        f.write(java_doc + "\n----\n" + method_code)

    # Generate oracle
    oracle = generate_oracle(method_code, java_doc, bug_report)
    if oracle is None:
        emitter.error("LLM interactor returned None as oracle")
        return None
    with open(values.file_extracted_oracle, "w", encoding="utf-8") as f:
        f.write(oracle)

    # Instrument method
    new_code_text = inject_oracle(code_lines, oracle, method_name, method_code, m_start, m_end)
    with open(values.dir_output / "instr.java", "w", encoding="utf-8") as f:
        f.write(new_code_text)

    return None

# Creates a prompt and sends it to llm_integration
def generate_oracle(method_code, java_doc, bug_report):
    prompt = (
        "Provide a test oracle from the following bug report. Do not give any further explanations. Do not print out any notes."
        "Do not use any formatting. Just print out the code itself. This is the bug report:\n" +
        bug_report +
        "\nThis is the oracle template you should use:\n" +
        llm_prompt_template +
        "\nThe wrapper methods name should be the same as the original method name, while the original method should be called method_original"
        "Do not print out the original method. Only print out the wrapper method."
        "This is the method you should instrument:\n" +
        java_doc + "\n" +
        method_code +
        "\nThis is one example how your instrumentation should look like:\n" +
        llm_prompt_example_1 +
        "\nThis is a second example of how your instrumentation should look like:\n" +
        llm_prompt_example_3
    )

    oracle_code = llm_integration.call_llm(prompt).strip()

    # Remove everything around the codeblock, if it exists
    codeblock_pattern = re.compile(
        r'^\s*```(?:java)?\s*\n'  # Open codeblock with ``` or ```java
        r'([\s\S]*?)'  # Everythin in between
        r'\n```',  # Close codeblock
        flags=re.MULTILINE
    )
    m = codeblock_pattern.search(oracle_code)
    if m:
        return m.group(1).strip()

    # When no code block is found, remove reasoning data, inside <think> block, if it exists
    thinking_pattern = re.compile(r'<think>[\s\S]*?</think>', flags=re.IGNORECASE)
    cleaned = thinking_pattern.sub('', oracle_code).strip()

    return cleaned

# Spectra gives us the most suspicious line of code, but we need the whole method. This function provides it.
def extract_method(location, code_lines, code_text):
    tree = javalang.parse.parse(code_text)

    for _, method_node in tree.filter(javalang.tree.MethodDeclaration):
        # Node position is method header
        header_start_line = method_node.position.line if method_node.position else None
        if header_start_line is None:
            emitter.warning(f"header_start_line is None")
            continue

        # Extract all lines from the header start line to the line of the closing token
        m_start, m_end = get_method_start_end(code_text, header_start_line)
        extracted_lines = code_lines[m_start - 1: m_end]
        method_code = "".join(extracted_lines)

        # Retrieve the JavaDoc from the AST, if available
        java_doc = getattr(method_node, "documentation", "")
        if java_doc and not java_doc.startswith("/**"):
            java_doc = f"/**\n{java_doc}\n*/\n"

        # Check if the suspicious line falls within the extracted methods range.
        if m_start <= location.line_number <= m_end:
            emitter.debug(f"Method line range: {m_start} - {m_end}")
            return java_doc, method_node.name, method_code, m_start, m_end
    emitter.warning(f"Could not find suspicious method at location {location}")
    return None

# This function determines a methods start and end line, given a method header line and the entire files source code
def get_method_start_end(code_text, header_start_line):
    # Tokenize the entire source code.
    tokens = list(javalang.tokenizer.tokenize(code_text))
    m_start = header_start_line

    # Find the first '{' token
    start_idx = None
    for i, token in enumerate(tokens):
        if token.value == "{" and token.position[0] >= header_start_line:
            start_idx = i
            break
    if start_idx is None: # No opening brace found
        return "", header_start_line, header_start_line, header_start_line

    # Count braces starting at the found token
    brace_count = 0
    method_token_end = None
    for token in tokens[start_idx:]:
        if token.value == "{":
            brace_count += 1
        elif token.value == "}":
            brace_count -= 1

        if brace_count == 0: # If counter hits 0 again, the method is closed
            method_token_end = token
            break
    if method_token_end is None: # Fallback: use the last token if no balance is found. TODO: Maybe the program should exit here?
        method_token_end = tokens[-1]
    m_end = method_token_end.position[0]

    return m_start, m_end

def inject_oracle(code_lines, oracle_code, method_name, method_code, m_start, m_end):
    original_method_code = rename_method_in_text(method_code, method_name)

    injection_block = (
        "\n\n################\n# ORACLE\n################\n\n" +
        oracle_code +
        "\n\n################\n# ORIGINAL METHOD\n################\n\n" +
        original_method_code.strip() +
        "\n\n"
    )

    # Replace the lines from m_start - 1 to m_end in code_lines with the injection block.
    new_code_lines = code_lines[:m_start - 1] + [injection_block] + code_lines[m_end:]
    new_code_text = "".join(new_code_lines)

    return new_code_text

# Renames a java method from "method_name" to "method_name_original"
def rename_method_in_text(method_code, original_name):
    lines = method_code.splitlines(keepends=True)

    # Pattern to match a typical Java method declaration line.
    # This regular expression assumes the declaration starts with some access modifiers (public, private, etc.)
    # followed by a return type and then the method name. The method name is then followed by whitespace
    # and an opening parenthesis.
    pattern = re.compile(
        r'^(?P<indent>\s*(?:public|protected|private|static|final|synchronized|\s)+\s+[\w\<\>\[\]]+\s+)' +
        re.escape(original_name) +
        r'(\s*\(.*)$'
    )

    replaced = False
    for i, line in enumerate(lines):
        # Try matching a proper method declaration
        match = pattern.match(line)
        if match:
            # Build the new line, replacing the original method name with <name>_original
            new_line = match.group('indent') + original_name + "_original" + match.group(2)
            lines[i] = new_line
            replaced = True
            break

    if not replaced:
        # Fallback: Find the first non-comment line that contains '(' and the method name.
        emitter.warning("Using fallback for rename method name")
        for i, line in enumerate(lines):
            # Skip typical comment lines
            stripped = line.strip()
            if stripped.startswith("/*") or stripped.startswith("*") or stripped.startswith("//"):
                continue
            if '(' in line and original_name in line:
                new_line = re.sub(r'\b' + re.escape(original_name) + r'\b', original_name + "_original", line, count=1)
                lines[i] = new_line
                replaced = True
                break

    return ''.join(lines)
