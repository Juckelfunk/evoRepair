# Returns oracle
import os
from pathlib import Path

from app import values, spectra, emitter
import javalang

def extract_oracle(spectra):
    # Print out bug report
    # TODO: More robust file handling (especially when no file was found)
    print(values.file_bug_report)
    with open(values.file_bug_report, 'r') as file:
        content = file.read()
        print(content)

    # Get sus location
    location = spectra.get_top_suspicious_location()
    emitter.information(f"Suspicious location: {location}")
    method = extract_method_from_definition(location)
    print(f"Suspicious method:\n{method}")

    return None

# Spectra gives the most suspicious line of code, but we need the whole method. This function provides it.
def extract_method_from_definition(location):
    emitter.debug(f"Target class: {location.class_name}")
    emitter.debug(f"Suspicious line: {location.line_number}")

    # Read in suspicious Java file
    parts = location.class_name.split('.')
    target_file = Path(values.dir_info["source"], *parts).with_suffix(".java")
    assert os.path.isfile(target_file), target_file

    with open(target_file, 'r') as f:
        codelines = f.readlines()
        code_text = ''.join(codelines)

    # Extract all methods from java file
    # This seems quite inefficient for what we need. We already know the suspicious line, so we could just extract the
    # surrounding method. However, this code extracts every method from the file.
    lex = None
    tree = javalang.parse.parse(code_text)
    methods = {}
    for _, method_node in tree.filter(javalang.tree.MethodDeclaration):
        startpos, endpos, startline, endline = get_method_start_end(method_node, tree)
        method_text, startline, endline, lex = get_method_text(startpos, endpos, startline, endline, lex, codelines)
        methods[method_node.name] = method_text

        # FIXME: method text might contain parts of javadoc comment. It should be either fully included or completely excluded
        # * @see #getLegendItem(int, int)
        # */
        # public LegendItemCollection getLegendItems() {
        if startline <= location.line_number <= endline:
            emitter.debug(f"Method line range: {startline} - {endline}")
            return method_text

"""
From https://github.com/c2nes/javalang/issues/49
Accessed 08.04.2025
"""

def get_method_start_end(method_node, tree):
    startpos  = None
    endpos    = None
    startline = None
    endline   = None
    for path, node in tree:
        if startpos is not None and method_node not in path:
            endpos = node.position
            endline = node.position.line if node.position is not None else None
            break
        if startpos is None and node == method_node:
            startpos = node.position
            startline = node.position.line if node.position is not None else None
    return startpos, endpos, startline, endline

def get_method_text(startpos, endpos, startline, endline, last_endline_index, codelines):
    if startpos is None:
        return "", None, None, None
    else:
        startline_index = startline - 1
        endline_index = endline - 1 if endpos is not None else None

        # 1. check for and fetch annotations
        if last_endline_index is not None:
            for line in codelines[(last_endline_index + 1):(startline_index)]:
                if "@" in line:
                    startline_index = startline_index - 1
        meth_text = "<ST>".join(codelines[startline_index:endline_index])
        meth_text = meth_text[:meth_text.rfind("}") + 1]

        # 2. remove trailing rbrace for last methods & any external content/comments
        # if endpos is None and
        if not abs(meth_text.count("}") - meth_text.count("{")) == 0:
            # imbalanced braces
            brace_diff = abs(meth_text.count("}") - meth_text.count("{"))

            for _ in range(brace_diff):
                meth_text  = meth_text[:meth_text.rfind("}")]
                meth_text  = meth_text[:meth_text.rfind("}") + 1]

        meth_lines = meth_text.split("<ST>")
        meth_text  = "".join(meth_lines)
        last_endline_index = startline_index + (len(meth_lines) - 1)

        return meth_text, (startline_index + 1), (last_endline_index + 1), last_endline_index