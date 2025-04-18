# Returns oracle
import os
import re
from pathlib import Path

from app import values, spectra, emitter, llm_integration
import javalang

def extract_oracle(spectra):
    # Read bug report
    if Path(values.file_bug_report).is_file():
        emitter.debug(f"Found bug report at: {values.file_bug_report}")
        with open(values.file_bug_report, 'r') as file:
            bug_report = file.read()
    else:
        emitter.error(f"Bug report file not found at expected location: {values.file_bug_report}")
        return # TODO: Program should exit here

    # Get sus location
    location = spectra.get_top_suspicious_location()
    emitter.information(f"Suspicious location: {location}")

    # Read in suspicious Java file
    parts = location.class_name.split('.')
    target_file = Path(values.dir_info["source"], *parts).with_suffix(".java")
    assert os.path.isfile(target_file), target_file
    with open(target_file, 'r') as f: # TODO: More robust file handling
        code_lines = f.readlines()
        code_text = ''.join(code_lines)

    # Extract method code
    java_doc, method_name, method_code, m_start, m_end = extract_method(location, code_lines, code_text)
    emitter.information(f"Extracted method:\n{java_doc}\n{method_code}")

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

# Creates prompt and sends it to llm_integration
def generate_oracle(method_code, java_doc, bug_report):
    template = (
        "T wrapper_method(Parameters p ...) {\n"
        "  if (Boolean.parseBoolean(System.getProperty(\"defects4j.instrumentation.enabled\") {\n"
        "    T result = original_method(p);\n"
        "    if (<condition_for_buggy_behavior>) {\n"
        "      throw new RuntimeException(\"[Defects4J_BugReport_Violation]\");\n"
        "    }\n"
        "    return result;\n"
        "  } else {\n"
        "    return original_method(p);\n"
        "  }\n"
        "}\n"
    )

    # Chart 1
    example1 = (
        "public LegendItemCollection getLegendItems() {\n"
        "  if (Boolean.parseBoolean(System.getProperty(\"defects4j.instrumentation.enabled\"))) {\n"
        "    try {\n"
        "      return getLegendItems_original();\n"
        "    } catch (NullPointerException e) {\n"
        "        throw new RuntimeException(\"[Defects4J_BugReport_Violation]\");\n"
        "    }\n"
        "  } else {\n"
        "    return getLegendItems_original();\n"
        "  }\n"
        "}\n"
    )

    # Time 4
    example2 = (
        "public Partial with(DateTimeFieldType fieldType, int value) {\n"
        "  if (Boolean.parseBoolean(System.getProperty(\"defects4j.instrumentation.enabled\"))) {\n"
        "    Partial result = with_original(fieldType, value);\n"
        "    try {\n"
        "      new Partial(result.getFieldTypes(), result.getValues());\n"
        "    } catch (IllegalArgumentException e1) {\n"
        "      throw new RuntimeException(\"[Defects4J_BugReport_Violation]\");\n"
        "    }\n"
        "    return result;\n"
        "  } else {\n"
        "    return with_original(fieldType, value);\n"
        "  }\n"
        "}\n"
    )

    prompt = (
        "Generate a test oracle from the following bug report. Do not give any further explanations. Do not print out any notes."
        "Do not use any formatting. Just print out the code itself. This is the bug report:\n" +
        bug_report +
        "\nThis is the oracle template you should use:\n" +
        template +
        "\nThe wrapper methods name should be the same as the original method name, while the original method should be called method_original"
        "Do not print out the original method. Only print out the wrapper method."
        "This is the method you should instrument:\n" +
        java_doc + "\n" +
        method_code +
        "\nThis is one example how your instrumentation should look like:\n" +
        example1 +
        "\nThis is a second example of how your instrumentation should look like:\n" +
        example2
    )

    oracle_code = llm_integration.call_llm(prompt).strip()

    # Remove reasoning data, if it exists
    oracle_code = re.sub(r"<think>.*?</think>", "", oracle_code, flags=re.DOTALL).strip()

    # Strip code block notation if it exists
    start_marker = "```java\n" # TODO: Sometimes the code block does not specify java
    end_marker = "\n```"
    if oracle_code.startswith(start_marker) and oracle_code.endswith(end_marker):
        oracle_code = oracle_code[len(start_marker):-len(end_marker)].strip()

    return oracle_code

# Spectra gives us the most suspicious line of code, but we need the whole method. This function provides it.
def extract_method(location, code_lines, code_text):
    tree = javalang.parse.parse(code_text)

    for _, method_node in tree.filter(javalang.tree.MethodDeclaration):
        # Node position is method header
        header_start_line = method_node.position.line if method_node.position else None
        if header_start_line is None:
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
