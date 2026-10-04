from cvit.constants import WELCOME_TEXT

BASIC_PLACEHOLDER = b"CV\x00\x20\x00\x20\x00\x00BASIC placeholder\r" * 8
CED_PLACEHOLDER = b"CV\x00\x20\x00\x20\x00\x00CED is resident in COMMAND via SVC $50\r" * 4
TEST_PLACEHOLDER = b"TEST is a preallocated cvit CED save target.\r".ljust(400, b" ")
ZEP_PLACEHOLDER = b"ZEP is a preallocated cvit CED save target.\r".ljust(400, b" ")


def generated_members(kernel, command):
    return {
        "kernel.bin": kernel,
        "welcome.txt": WELCOME_TEXT,
        "basic.bin": BASIC_PLACEHOLDER,
        "ced.bin": CED_PLACEHOLDER,
        "test.txt": TEST_PLACEHOLDER,
        "zep.txt": ZEP_PLACEHOLDER,
        "command.bin": command,
    }
