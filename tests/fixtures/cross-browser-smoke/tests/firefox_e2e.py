"""Prove shared popup behavior in temporary Firefox installation."""


def run(context):
    driver = context["driver"]
    driver.get(context["extension_origin"] + "/src/popup.html")
    heading = driver.find_element("css selector", "h1")
    ready = driver.find_element("css selector", '[data-testid="ready"]')
    assert heading.text == context["manifest"]["name"]
    assert ready.text == "Shared extension runtime ready."
    assert ready.get_attribute("data-initialized") == "true"
    return {"limitations": [], "criteriaPassed": ["REQ-001"]}
