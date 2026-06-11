{
    "name": "LLM Tool Product",
    "version": "18.0.1.0.0",
    "category": "Productivity/LLM",
    "summary": "Semantic product search tool for AI assistants",
    "description": """
        LLM Tool Product - Semantic Product Search

        Embeds the saleable product catalog into a vector collection and
        exposes an `odoo_product_search` tool so AI assistants can find
        products by describing what the customer wants, instead of
        requiring exact names or codes.
    """,
    "author": "Apexive Solutions LLC",
    "website": "https://github.com/apexive/odoo-llm",
    "license": "LGPL-3",
    "depends": [
        "product",
        "llm_tool",
        "llm_knowledge",
        "llm_pgvector",
        "llm_skills",
    ],
    "data": [
        "data/llm_collection_data.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
