import hashlib
import logging

from odoo import api, models

from odoo.addons.llm_tool.decorators import llm_tool

_logger = logging.getLogger(__name__)

_COLLECTION_XMLID = "llm_tool_product.llm_collection_product_catalog"

# Fields that affect the embedded catalog content or its eligibility.
_LLM_SYNC_FIELDS = {
    "name",
    "description_sale",
    "list_price",
    "categ_id",
    "sale_ok",
    "active",
}

# Arbitrary constant for pg_try_advisory_xact_lock — distinct from other
# modules' boot-sync locks (e.g. llm_skills uses 853271649).
_BACKFILL_LOCK_KEY = 904512233

# xmlid registered (if missing) for the Nomic Atlas API embedding model, so
# the collection's embedding_model_id can reference it via env.ref().
_NOMIC_API_MODEL_XMLID = "nomic_embed_text_v1_5_api"


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # -------------------------------------------------------------------------
    # Catalog embedding sync
    # -------------------------------------------------------------------------

    def _llm_catalog_content(self):
        """Build the text embedded for semantic product search."""
        self.ensure_one()
        parts = [self.name]
        if self.description_sale:
            parts.append(self.description_sale)
        if self.categ_id:
            parts.append(f"Category: {self.categ_id.name}")
        parts.append(f"Price: {self.list_price} {self.currency_id.name}")
        return "\n".join(parts)

    def _sync_llm_catalog_chunk(self):
        """Upsert this product's chunk in the "Product Catalog" collection.

        Skips/removes the chunk for non-saleable or archived products. Uses a
        SHA-256 content hash (stored in chunk metadata) to avoid re-embedding
        unchanged products.
        """
        self.ensure_one()
        collection = self.env.ref(_COLLECTION_XMLID, raise_if_not_found=False)
        if not collection:
            _logger.debug(
                "llm_tool_product: collection '%s' not found — skipping sync",
                _COLLECTION_XMLID,
            )
            return

        ProductModel = self.env["ir.model"]._get("product.template")
        resource = self.env["llm.resource"].search(
            [
                ("model_id", "=", ProductModel.id),
                ("res_id", "=", self.id),
            ],
            limit=1,
        )

        if not self.sale_ok or not self.active:
            if resource:
                resource.unlink()
            return

        content = self._llm_catalog_content()
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        if not resource:
            resource = self.env["llm.resource"].create(
                {
                    "name": self.name,
                    "model_id": ProductModel.id,
                    "res_id": self.id,
                    "state": "ready",
                    "collection_ids": [(4, collection.id)],
                }
            )
        elif resource.collection_ids - collection:
            # Chunks are shared across all of a resource's collections
            # (llm.knowledge.chunk.collection_ids is related to
            # resource_id.collection_ids). Rewriting chunk content here would
            # corrupt embeddings for whatever other collection already owns
            # this resource — leave it alone.
            _logger.info(
                "llm_tool_product: skipping product %s — its llm.resource is "
                "already managed by collection(s) %s",
                self.id,
                ", ".join(resource.collection_ids.mapped("name")),
            )
            return
        elif collection.id not in resource.collection_ids.ids:
            resource.collection_ids = [(4, collection.id)]

        existing_chunk = self.env["llm.knowledge.chunk"].search(
            [
                ("resource_id", "=", resource.id),
            ],
            limit=1,
        )
        if (
            existing_chunk
            and (existing_chunk.metadata or {}).get("content_hash") == content_hash
        ):
            return

        existing_chunk.unlink()
        self.env["llm.knowledge.chunk"].create(
            {
                "resource_id": resource.id,
                "content": content,
                "sequence": 1,
                "metadata": {"product_id": self.id, "content_hash": content_hash},
            }
        )

        try:
            collection.embed_resources(specific_resource_ids=[resource.id])
        except Exception:
            _logger.exception(
                "llm_tool_product: embedding failed for product %s", self.id
            )

    @api.model_create_multi
    def create(self, vals_list):
        products = super().create(vals_list)
        for product in products:
            product._sync_llm_catalog_chunk()
        return products

    def write(self, vals):
        res = super().write(vals)
        if _LLM_SYNC_FIELDS & set(vals):
            for product in self:
                product._sync_llm_catalog_chunk()
        return res

    def unlink(self):
        ProductModel = self.env["ir.model"]._get("product.template")
        resources = self.env["llm.resource"].search(
            [
                ("model_id", "=", ProductModel.id),
                ("res_id", "in", self.ids),
            ]
        )
        resources.unlink()
        return super().unlink()

    @api.model
    def _switch_to_nomic_api_embedding_model(self):
        """Prefer the hosted Nomic Atlas API embedding model, if configured.

        In dev/test environments the Ollama provider's api_base
        (host.docker.internal) is often unreachable from inside containers,
        so embeddings silently never complete. The Nomic Atlas API is a
        normal HTTPS call and works regardless. If a 'nomic' service
        provider with an embedding model is configured, switch the
        collection to use it instead of the Ollama default.
        """
        collection = self.env.ref(_COLLECTION_XMLID, raise_if_not_found=False)
        if not collection:
            return

        nomic_model = self.env["llm.model"].search(
            [
                ("provider_id.service", "=", "nomic"),
                ("model_use", "=", "embedding"),
            ],
            limit=1,
        )
        if not nomic_model or collection.embedding_model_id == nomic_model:
            return

        IrModelData = self.env["ir.model.data"]
        if not IrModelData.search(
            [
                ("module", "=", "llm_tool_product"),
                ("name", "=", _NOMIC_API_MODEL_XMLID),
            ],
            limit=1,
        ):
            IrModelData.create(
                {
                    "name": _NOMIC_API_MODEL_XMLID,
                    "module": "llm_tool_product",
                    "model": "llm.model",
                    "res_id": nomic_model.id,
                    "noupdate": True,
                }
            )

        _logger.info(
            "llm_tool_product: switching 'Product Catalog' embedding model to "
            "Nomic API model '%s' (id=%s)",
            nomic_model.name,
            nomic_model.id,
        )
        collection.embedding_model_id = nomic_model.id

    @api.model
    def _register_hook(self):
        """Backfill catalog chunks for existing products on install/upgrade.

        Hash-based change detection in _sync_llm_catalog_chunk makes repeated
        runs cheap. The advisory lock ensures only one worker does the backfill
        on a given boot.
        """
        super()._register_hook()

        self.env.cr.execute(
            "SELECT pg_try_advisory_xact_lock(%s)", (_BACKFILL_LOCK_KEY,)
        )
        if not self.env.cr.fetchone()[0]:
            return

        self._switch_to_nomic_api_embedding_model()

        products = self.search([("sale_ok", "=", True), ("active", "=", True)])
        for product in products:
            try:
                product._sync_llm_catalog_chunk()
            except Exception:
                _logger.exception(
                    "llm_tool_product: backfill sync failed for product %s", product.id
                )

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
        collection = self.env.ref(_COLLECTION_XMLID, raise_if_not_found=False)
        if not collection:
            _logger.warning(
                "odoo_product_search: collection '%s' not found", _COLLECTION_XMLID
            )
            return []

        try:
            chunks = self.env["llm.knowledge.chunk"].search(
                args=[("embedding", "=", query)],
                limit=limit * 3,
                collection_id=collection.id,
                query_min_similarity=0.5,
            )
        except Exception:
            _logger.exception("odoo_product_search: vector search failed")
            return []

        results = []
        seen_ids = set()
        for chunk in chunks:
            resource = chunk.resource_id
            if not resource or resource.res_model != "product.template":
                continue
            product_id = resource.res_id
            if product_id in seen_ids:
                continue
            seen_ids.add(product_id)

            product = self.browse(product_id)
            if not product.exists():
                continue

            results.append(
                {
                    "id": product.id,
                    "name": product.name,
                    "list_price": product.list_price,
                    "category": product.categ_id.name,
                    "description": product.description_sale or "",
                }
            )
            if len(results) >= limit:
                break

        return results
