"""Tailor this scenario to requested behavior before final verification."""


def run(context):
    driver = context["driver"]
    driver.get(context["extension_origin"] + "/src/popup.html")
    ready = driver.find_element("css selector", '[data-testid="ready"]')
    assert ready.get_attribute("data-initialized") == "true"
    return {"activeTabProven": False, "criteriaPassed": []}
