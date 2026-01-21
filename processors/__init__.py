"""
processors package

Processing pipeline that converts raw ChatGPT export JSON into a normalized,
enriched tree format that renderers can use.

To run:

python -m processors.convert [INPUT_JSON] --out [OUTPUT_JSON]

Intended future run:

python -m processors.convert data/conversations.json --out output/processed.json

Currently:

python -m processors.convert examples/test_conversations.json --out examples/test_processed_from_convert.json

Sample result in CLI:

========================================================================
Conversion complete
========================================================================
Input:  examples/test_conversations.json
Output: examples/test_processed_from_convert.json
Conversations: 3

"""

