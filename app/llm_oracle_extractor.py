# Returns oracle
from app import values, spectra, emitter


def extract_oracle(spectra):
    # Print out bug report
    print(values.file_bug_report)
    with open(values.file_bug_report, 'r') as file:
        content = file.read()
        print(content)

    # Get sus location
    location = spectra.get_top_suspicious_location()
    emitter.information(f"Suspicious location: {location}")
    method = extract_method_from_definition(location)

    return None

# Spectra gives the most suspicious line of code, but we need the whole method. This function provides it.
def extract_method_from_definition(location):

    pass
