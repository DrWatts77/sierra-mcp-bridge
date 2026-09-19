from importlib.resources import files

GUIDE = files('sierra_mcp_bridge').joinpath('operating_guide.md').read_text(encoding='utf-8')
TOOLSETS = {
    'discovery': {'enabled': True, 'tools': ['get_startup_context', 'list_charts', 'list_studies'],
                  'instructions': 'Start here. Select the authorized chart; discover current exported studies and resolve names/colors/inputs to an unambiguous key.'},
    'current_data': {'enabled': True, 'tools': ['get_snapshot', 'get_study_values'],
                     'instructions': 'Read current evidence for the selected chart/output. Respect timeframe, export age and unavailable values.'},
    'recent_history': {'enabled': True, 'tools': ['get_study_history'],
                       'instructions': 'Query the currently calculated loaded bars, bounded by the exporter\'s configured window (up to 200,000). Check timezone, coverage and forming state; no point-in-time claims.'},
    'footprint_health': {'enabled': True, 'tools': ['get_footprint', 'get_data_health'],
                         'instructions': 'Diagnose source/file quality and inspect bounded levels. Unknown bid/ask is not balanced flow.'},
    'account_reads': {'enabled': False, 'tools': [], 'instructions': 'Not implemented; do not infer positions, balances or P&L.'},
    'order_actions': {'enabled': False, 'tools': [], 'instructions': 'Not implemented or authorized by this bridge. Future controls must be enforced in code.'},
}
