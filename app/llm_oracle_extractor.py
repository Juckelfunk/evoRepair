# Returns oracle
import os
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
    java_doc, method = extract_method_from_line(location)
    print(java_doc)
    print("----")
    print(method)

    with open(values.dir_output / "extract.java", "w", encoding="utf-8") as f:
        f.write(java_doc + "\n----\n" + method)

    # oracle = generate_oracle(method, bug_report)
    #
    # if oracle is None:
    #     emitter.error("LLM interactor returned None as oracle")
    #     return None
    #
    # with open(values.file_extracted_oracle, "w", encoding="utf-8") as f:
    #     f.write(oracle)
    #
    # return None

# Creates prompt and sends it to llm_integration
def generate_oracle(method, bug_report):
    template = (
        "T wrapper_method(Parameters p ...) {"
        "  if (Boolean.parseBoolean(System.getProperty(\"defects4j.instrumentation.enabled\") {"
        "    T result = original_method(p);"
        "    if (<condition_for_buggy_behavior>) {"
        "      throw new RuntimeException(\"[Defects4J_BugReport_Violation]\");"
        "    }"
        "    return result;"
        "  } else {"
        "    return original_method(p);"
        "  }"
        "}"
    )

    example1 = (
        "public LegendItemCollection getLegendItems() {"
        "  if (Boolean.parseBoolean(System.getProperty(\"defects4j.instrumentation.enabled\"))) {"
        "    try {"
        "      return getLegendItems_original();"
        "    } catch (NullPointerException e) {"
        "        throw new RuntimeException(\"[Defects4J_BugReport_Violation]\");"
        "    }"
        "  } else {"
        "    return getLegendItems_original();"
        "  }"
        "}"
    )

    example2 = (
        "public Partial with(DateTimeFieldType fieldType, int value) {"
        "  if (Boolean.parseBoolean(System.getProperty(\"defects4j.instrumentation.enabled\"))) {"
        "    Partial result = with_original(fieldType, value);"
        "    try {"
        "      new Partial(result.getFieldTypes(), result.getValues());"
        "    } catch (IllegalArgumentException e1) {"
        "      throw new RuntimeException(\"[Defects4J_BugReport_Violation]\");"
        "    }"
        "    return result;"
        "  } else {"
        "    return with_original(fieldType, value);"
        "  }"
        "}"
    )

    prompt = (
        "Generate a test oracle from the following bug report Do not give any further explanations. Do print out any notes."
        "Do not use any formatting. Just print out the code itself. This is the bug report:" +
        bug_report +
        "This is the oracle template you should use:" +
        template +
        "The wrapper methods name should be the same as the original method name, while the original method should be called method_original"
        "This is the method you should instrument:" +
        method +
        "This is the first example of an instrumentation you should implement:" +
        example1 +
        "This is a second example of an instrumentation you should implement:" +
        example2
    )

    return llm_integration.call_llm(prompt)

# Spectra gives us the most suspicious line of code, but we need the whole method. This function provides it.
def extract_method_from_line(location):
    emitter.debug(f"Target class: {location.class_name}")
    emitter.debug(f"Suspicious line: {location.line_number}")

    # Read in suspicious Java file
    parts = location.class_name.split('.')
    target_file = Path(values.dir_info["source"], *parts).with_suffix(".java")
    assert os.path.isfile(target_file), target_file

    with open(target_file, 'r') as f:
        codelines = f.readlines()
        code_text = ''.join(codelines)

    tree = javalang.parse.parse(code_text)

    for _, method_node in tree.filter(javalang.tree.MethodDeclaration):
        # Node position is method header
        header_start_line = method_node.position.line if method_node.position else None
        if header_start_line is None:
            continue
        method_text, m_start, m_end, _ = extract_method_using_tokens(code_text, code_lines, header_start_line)

        # Retrieve the JavaDoc from the AST, if available
        java_doc = getattr(method_node, "documentation", "")
        if java_doc and not java_doc.startswith("/**"):
            java_doc = f"/**\n{java_doc}\n*/\n"

        # Check if the suspicious line falls within the extracted method range.
        if m_start <= location.line_number <= m_end:
            emitter.debug(f"Method line range: {m_start} - {m_end}")
            return (java_doc, method_text)
    return None

# Extracts the entire method source code
def extract_method_using_tokens(code_text, code_lines, header_start_line):
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

        if brace_count == 0:
            method_token_end = token
            break
    if method_token_end is None: # Fallback: use the last token if no balance is found. TODO: Maybe the program should exit here?
        method_token_end = tokens[-1]
    m_end = method_token_end.position[0]

    # Extract all lines from the header start line to the line of the closing token
    extracted_lines = code_lines[m_start - 1: m_end]
    method_text = "".join(extracted_lines)

    return method_text, m_start, m_end, m_end
