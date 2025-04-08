import json

import requests

def generate_oracle(method, bug_report):
    url = "http://localhost:11434/api/generate"

    prompt = (
        "Generate a test oracle from this bug report:" +
        bug_report +
        "This is the oracle template you should use:"
        "T wrapper_method(Parameters p ...) {"
        "  if (instrumentation_enabled) {"
        "    T result = original_method(p);"
        "    if (<condition_for_buggy_behavior>) {"
        "      throw new RuntimeException(\"[Defects4J_BugReport_Violation]\");"
        "    }"
        "    return result;"
        " } else {"
        "    return original_method(p);"
        "  }"
        "}"
        "This is the method you should instrument:" +
        method
    )

    payload = {
        "model": "phi4",
        "prompt": prompt,
        "options": {"num_ctx": 4096}
    }

    try:
        response = requests.post(url, json=payload, stream=True)
        response.raise_for_status()
    except requests.RequestException as e:
        print("Error while sending prompt:", e)
        return

    full_answer = ""
    for line in response.iter_lines():
        if line:
            try:
                data = json.loads(line.decode("utf-8"))
                full_answer += data.get("response", "")
            except json.JSONDecodeError as e:
                print("Could not decode JSON line:", line, e)

    print("Answer:")
    print(full_answer)
