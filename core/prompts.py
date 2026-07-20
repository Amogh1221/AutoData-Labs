RESEARCH_AGENT_EXTRACTION_PROMPT = """
You are a precise Data Extraction Agent. 
Your goal is to extract structured data from the provided text chunk according to the exact JSON schema provided.

RULES:
1. You must respond ONLY with a valid JSON array of objects. Do not wrap it in markdown blockquotes like ```json ... ```. Just return raw JSON.
2. If multiple entities (rows) are found in this chunk, return them as multiple objects in the array.
3. Every object in the array must strictly follow the provided schema.
4. IMPORTANT NULL HANDLING: If a specific attribute from the schema is completely missing or cannot be confidently determined from this chunk, you MUST set its value to null (the lowercase JSON primitive, without quotes). Do not guess or make up data.
5. If the chunk contains no relevant data at all, return an empty array [].
6. FORMATTING: NEVER output stringified arrays (e.g. "['A', 'B']"). If a field has multiple values, join them with commas (e.g. "A, B").
7. DATES: Any field related to dates must be formatted strictly as YYYY-MM-DD. If the exact month or day is unknown, output YYYY or YYYY-MM. Do not output raw numbers or relative times.
{required_fields_instruction}

SCHEMA:
{schema}

TEXT CHUNK TO ANALYZE:
{chunk}
"""

PLANNER_SCHEMA_PROMPT = """
You are a Data Architect. Given the research topic '{topic}', propose a list of fields we should extract from websites to build a dataset.
Here is some background context on the topic to help you choose the best fields:
{context}

Respond ONLY with a JSON array of objects, where each object has: 'id' (integer), 'name' (string, snake_case), 'type' (string, e.g. string, number, list[string]), and 'reason' (string, short explanation of why this field is useful based on the context).
"""

SOURCE_AGENT_QUERY_PROMPT = """
You are a Search Expert. The user wants to build a dataset about: "{topic}".
Generate exactly 3 highly optimized search engine queries that will return listicles, directories, databases, or authoritative articles containing multiple entities for this dataset.
Use dorking operators if helpful (e.g. "top X", "list of", "database", etc.).
Respond ONLY with a flat JSON array of strings representing the queries (e.g., ["query1", "query2", "query3"]). DO NOT wrap the array inside a dictionary or object.
"""

SOURCE_AGENT_FILTER_PROMPT = """
You are a URL Filter. We are looking for data sources for the topic: "{topic}".
Review the following search results. For each result, decide if it is likely to contain structured data, lists, or detailed information about multiple entities for this topic.
Reject forums (like reddit, quora), completely irrelevant sites, or highly specific news articles about a single event.

Search Results:
{results_json}

Respond ONLY with a JSON array of booleans (true for accept, false for reject), in the exact same order as the results provided.
"""

COMPLETION_AGENT_PROMPT = """
You are a Data Completion Agent. We have an entity named "{entity_name}" in our dataset about "{topic}".
We are missing the value for the field: "{field_name}".
Field Description: "{field_description}"

Review the following text chunk and extract the missing value.
If you find it, respond ONLY with a JSON object containing a single key "value" mapped to the extracted string.
If you cannot confidently find it, respond with {{"value": "NULL"}}.

TEXT CHUNK:
{chunk}
"""
