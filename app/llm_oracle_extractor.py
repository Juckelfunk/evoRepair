# Returns oracle
import os
import re
from pathlib import Path

from app import values, spectra, emitter, llm_integration
import javalang

from app.values import llm_prompt_template, llm_prompt_example_1, llm_prompt_example_3, llm_prompt_example_1_bug_report, \
    llm_prompt_example_3_bug_report


def extract_oracle(spectra):
    ### Read bug report ###

    if Path(values.file_bug_report).is_file():
        emitter.debug(f"Found bug report at: {values.file_bug_report}")
        with open(values.file_bug_report, 'r') as file:
            bug_report = file.read()
    else:
        emitter.error(f"Bug report file not found at expected location: {values.file_bug_report}")
        return None


    ### Collect failing tests and their source ###

    failing_tests = [t for t, r in spectra.test_results.items() if r == "FAIL"]
    failing_tests_info = []

    test_dir = values.dir_exp + "/" + values.dir_test_src
    emitter.information(f"Looking for test source in {test_dir}")

    for test in failing_tests:
        try:
            class_name, method_name = test.split('#')
        except ValueError:
            emitter.error(f"Unrecognized test name format: {test}")
            continue

        # Construct test source file path under project/tests
        rel_path = Path(*class_name.split('.')).with_suffix('.java')
        test_file = test_dir / rel_path
        if not test_file.is_file():
            emitter.warning(f"Test source not found for {test}: expected at {test_file}")
            continue

        # Read and extract the specific method snippet
        code_lines = test_file.read_text(encoding='utf-8').splitlines(keepends=True)
        code_text = ''.join(code_lines)
        try:
            tree = javalang.parse.parse(code_text)
            for _, m in tree.filter(javalang.tree.MethodDeclaration):
                if m.name == method_name and m.position:
                    start, end = get_method_start_end(code_text, m.position.line)
                    snippet = ''.join(code_lines[start-1:end])
                    failing_tests_info.append((test, snippet))
                    break
        except Exception as ex:
            emitter.warning(f"Failed to parse test {test} in {test_file}: {ex}")

    # Log all failing tests and their source
    if failing_tests_info:
        for test, snippet in failing_tests_info:
            emitter.information(f"--- Failing Test: {test} ---")
            emitter.information(snippet)
    else:
        emitter.warning("No failing tests source to include")

    # Build context for failing tests, this will be included in LLM prompts
    tests_context = "\n\n".join(
        f"{i + 1}. {test}\n{snippet.strip()}"
        for i, (test, snippet) in enumerate(failing_tests_info)
    )

    # Let LLM select location
    chosen = select_location(spectra, bug_report, tests_context)

    # Prepare chosen method for oracle generation
    code_lines = chosen["code_lines"]
    java_doc = chosen["java_doc"]
    method_name = chosen["method_name"]
    method_code = chosen["method_code"]
    m_start = chosen["m_start"]
    m_end = chosen["m_end"]

    #### Generate oracle ####
    oracle = generate_oracle(method_code, java_doc, bug_report, tests_context)
    if oracle is None:
        emitter.error("LLM interactor returned None as oracle")
        return None
    with open(values.file_extracted_oracle, "w", encoding="utf-8") as f:
        f.write(oracle)

    #### Instrument method ####
    new_code_text = inject_oracle(code_lines, oracle, method_name, method_code, m_start, m_end)
    with open(values.dir_output / "instr.java", "w", encoding="utf-8") as f:
        f.write(new_code_text)

    return None

# Get top suspicious locations from spectra and let LLM choose the correct method to instrument
def select_location(spectra, bug_report, tests_context):
    #### Retrieve top suspicious locations ####

    locations = spectra.get_top_suspicious_locations(values.num_suspicious_locations)
    if not locations:
        emitter.error("No suspicious locations found")
        return None
    emitter.information(f"Retrieved top {len(locations)} suspicious locations:")
    for loc in locations:
        emitter.debug(f"{loc}")

    # Build context for selection prompt
    suspicious_locations_context = "\n".join(
        f"{i + 1}. {loc.class_name}:{loc.line_number}"
        for i, loc in enumerate(locations)
    )

    candidates = []
    # Gather unique method metadata for each candidate
    for i, loc in enumerate(locations):
        # Skip if this location is already covered by a kept candidate
        if any(c["m_start"] <= loc.line_number <= c["m_end"] for c in candidates):
            emitter.debug(f"Skipping duplicate candidate {i + 1} – location already covered")
            continue

        # Resolve file for inner classes
        parts = loc.class_name.split('.')
        raw = parts[-1]
        outer = raw.split('$', 1)[0] # Inner classes are marked with $ in the class name
        target_file = Path(values.dir_info["source"], *parts[:-1], outer).with_suffix(".java")
        if not os.path.isfile(target_file):
            emitter.warning(f"Candidate {i + 1} file not found: {target_file}")
            continue
        with open(target_file, 'r', encoding='utf-8') as f:
            code_lines = f.readlines()
            code_text = ''.join(code_lines)

        # Extract method containing the suspicious location
        extract = extract_method(loc, code_lines, code_text)
        if not extract:
            emitter.warning(f"Could not extract method for candidate {i + 1} at {loc}")
            continue
        java_doc, method_name, method_code, m_start, m_end = extract

        # Build complete signature up to the opening brace
        sig_lines = []
        for line in method_code.splitlines():
            if '{' in line:
                sig_lines.append(line.split('{')[0].strip())
                break
            sig_lines.append(line.strip())
        signature = " ".join(sig_lines).strip()

        # Debug: output full extracted method
        emitter.information(f"Candidate {i + 1} signature: {signature}")

        candidates.append({
            "index": len(candidates) + 1,
            "location": loc,
            "code_lines": code_lines,
            "java_doc": java_doc,
            "method_name": method_name,
            "method_code": method_code,
            "m_start": m_start,
            "m_end": m_end,
            "signature": signature,
        })

    #### Select Candidate ####
    if not candidates:
        emitter.error("No valid candidate methods extracted after filtering duplicates")
        return None

    # Contains all methods JavaDoc and implementation
    method_selection = [
        f"{cand['index']}. {cand['java_doc']}\n{cand['method_code']}"
        for cand in candidates
    ]

    selection_prompt = (
        f"Given the following bug report and suspicious code locations and failing test(s), select the single most likely "
        f"method signature from the candidate list that needs to be instrumented or modified to fix the bug.\n\n"
        f"Bug Report:\n------\n{bug_report}\n------\n\n"
        f"Failing Tests:\n------\n{tests_context}\n------\n\n"
        # f"Top {len(locations)} Suspicious Locations:\n------\n{suspicious_locations_context}\n------\n\n"
        f"Candidate Methods:\n------\n"
        f"{''.join(method_selection)}"
        f"------\n\n"
        f"Output *only* the full method signature line of the single most likely method from the list above. "
        f"Do not include the opening curly brace '{{'. Do not include any other text, explanations, or formatting."
    )

    chosen = None
    for attempt in range(1, 4):
        selected_signature = llm_integration.call_llm(selection_prompt, values.llm_selection_override).strip()
        selected_signature = clean_response(selected_signature)
        selected_signature = re.sub(r"\s*\{\s*$", "", selected_signature).strip() # Remove {

        emitter.information(f"Selected signature: {selected_signature}")
        chosen = next((c for c in candidates if c["signature"] == selected_signature), None)
        if not chosen:
            emitter.warning(f"Selected signature not matched on attempt {attempt}: {selected_signature}")
            continue

    if not chosen:
        emitter.warning(f"Selected signature not matched: using most suspicious location as fallback")
        return candidates[0]

    return chosen

# Creates a prompt and sends it to llm_integration
def generate_oracle(method_code, java_doc, bug_report, tests_context):
    prompt = f"""
    ### Instructions  
    1. Produce exactly one Java wrapper method.  
    2. Name it **exactly** like the original (no `method_original` rename).  
    3. Call the old code via `method_original(…)`.  
    4. Insert your **boolean condition** and any **extra logic** (inside or outside the `if`) to detect the bug, then throw `RuntimeException("[Defects4J_BugReport_Violation]")`.  
    5. Return **only** a java block—no prose, no comments, no imports.  

    ---

    ### Oracle template  
    ```java
    {llm_prompt_template}
    ````

    ---

    ### Example 1 (bug → wrapper)

    **Bug report:**
    *{llm_prompt_example_1_bug_report}*

    **Wrapper:**

    ```java
    {llm_prompt_example_1}
    ```

    ---

    ### Example 2 (bug → wrapper)

    **Bug report:**
    *{llm_prompt_example_3_bug_report}*

    **Wrapper:**

    ```java
    {llm_prompt_example_3}
    ```

    ---

    ### Your task

    **Bug report:**
    {bug_report}
    
    **Failing Test(s)**
    {tests_context}

    **Method to instrument (with javadoc):**
    {java_doc}
    {method_code}

    Replace `<condition_for_buggy_behavior>` and add any surrounding logic needed, then output **one** fenced `java block` containing only your wrapper method.
    """

    oracle_code = llm_integration.call_llm(prompt, values.llm_generation_override).strip()

    # Remove everything around the codeblock, if it exists
    return clean_response(oracle_code)

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

# Takes an LLM response, and removes everything around a code block (incl. the code block itself)
def clean_response(response):
    codeblock_pattern = re.compile(
        r'^\s*```(?:java)?\s*\n'  # Open codeblock with ``` or ```java
        r'([\s\S]*?)'  # Everythin in between
        r'\n```',  # Close codeblock
        flags=re.MULTILINE
    )
    m = codeblock_pattern.search(response)
    if m:
        return m.group(1).strip()

    # When no code block is found, remove reasoning data, inside <think> block, if it exists
    thinking_pattern = re.compile(r'<think>[\s\S]*?</think>', flags=re.IGNORECASE)
    cleaned = thinking_pattern.sub('', response).strip()
    return cleaned
