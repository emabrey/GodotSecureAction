extends Node

# This constant is the canary value for the reverse-engineering resistance test.
# If gdsdecomp (or any other tool) can recover this string from the exported
# project, the integration test will fail.
const INTEGRATION_TEST_SECRET := "gs_secret_tk9v2x8m4p7n1q3r5w"

func _ready() -> void:
    print("godot_secure_test_project: secret loaded, quitting.")
    get_tree().quit()
