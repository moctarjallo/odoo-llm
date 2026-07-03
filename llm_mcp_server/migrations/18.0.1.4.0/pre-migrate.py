def migrate(cr, version):
    """Backfill endpoint_path='/mcp' for existing config records."""
    cr.execute("""
        ALTER TABLE llm_mcp_server_config
        ADD COLUMN IF NOT EXISTS endpoint_path VARCHAR DEFAULT '/mcp';
    """)
    cr.execute("""
        UPDATE llm_mcp_server_config
        SET endpoint_path = '/mcp'
        WHERE endpoint_path IS NULL OR endpoint_path = '';
    """)
