import logging

from odoo import models

from odoo.addons.llm_tool.decorators import llm_tool

_logger = logging.getLogger(__name__)

_ASSISTANT_XMLID = "llm_tool_product.product_assistant"


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # -------------------------------------------------------------------------
    # LLM tool
    # -------------------------------------------------------------------------

    @llm_tool(read_only_hint=True, idempotent_hint=True)
    def odoo_product_search(self, query: str, limit: int = 10) -> list:
        """Search the saleable product catalog by describing what the customer wants.

        Use this to find products matching a customer's stated need before
        proposing them or building a quotation. Pass a short, concrete
        description of what they're looking for — not their exact words.

        Args:
            query: Plain-language description of the desired product.
            limit: Maximum number of products to return.

        Returns:
            List of dicts: [{id, name, list_price, category, description}]
        """
        products = self.search([("sale_ok", "=", True), ("active", "=", True)])
        if not products:
            return []

        catalog_lines = [
            f"- id={p.id}: {p.name} | Category: {p.categ_id.name} | "
            f"Price: {p.list_price} {p.currency_id.name} | {p.description_sale or ''}"
            for p in products
        ]
        user_content = "Customer request: {}\n\nCatalog:\n{}".format(
            query, "\n".join(catalog_lines)
        )

        assistant = self.env.ref(_ASSISTANT_XMLID, raise_if_not_found=False)
        result = (
            assistant.structured_chat("PRODUCT_SEARCH", user_content)
            if assistant
            else None
        )

        if result is not None and result.get("product_ids") is not None:
            ids_in_order = [pid for pid in result["product_ids"] if pid in products.ids]
            matched = products.browse(ids_in_order)
        else:
            # Fallback: assistant unavailable/misconfigured — plain keyword match.
            query_lower = query.lower()
            matched = products.filtered(
                lambda p: query_lower in p.name.lower()
                or query_lower in (p.description_sale or "").lower()
            )

        return [
            {
                "id": p.id,
                "name": p.name,
                "list_price": p.list_price,
                "category": p.categ_id.name,
                "description": p.description_sale or "",
            }
            for p in matched[:limit]
        ]
