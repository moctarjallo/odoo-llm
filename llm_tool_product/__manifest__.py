{
    "name": "LLM Tool Product",
    "version": "18.0.1.0.0",
    "category": "Productivity/LLM",
    "summary": "Product catalog search tool for AI assistants",
    "description": """
        LLM Tool Product - Product Catalog Search

        Exposes an `odoo_product_search` tool so AI assistants can find
        saleable products by describing what the customer wants, instead of
        requiring exact names or codes. Uses an LLM assistant to match the
        customer's request against the product catalog.
    """,
    "author": "Apexive Solutions LLC",
    "website": "https://github.com/apexive/odoo-llm",
    "license": "LGPL-3",
    "depends": [
        "product",
        "llm_tool",
        "llm_assistant",
        "llm_odoo",
    ],
    "data": [
        "data/llm_product_prompt.xml",
        "data/llm_product_assistant.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
