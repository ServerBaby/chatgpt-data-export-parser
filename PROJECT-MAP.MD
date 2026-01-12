# PROJECT FILE MAP (ChatGPT Data Export Parser)

## Purpose of this note

This document describes the recommended file and folder layout for the
"ChatGPT Data Export Parser" project, and explains what each part does in
plain language. The goal is to keep the project professional, resume-friendly,
and easy to expand later without rewriting everything.

## Core design idea (the main principle)

The project should follow this simple rule:

```
Parse once, render many times.
```

Meaning:

* The tool should read and understand the exported JSON data only once.
* Then it should be able to output that same data in different formats
  (TXT, Markdown, HTML, etc.) without re-parsing or duplicating logic.

This is why the project is split into:

1. Parsing logic (reading and understanding the export)
2. A neutral internal data model (a clean structure in code)
3. Rendering logic (turning the model into different output formats)
4. A small "runner" script that ties it all together

## Current baseline files (what already exists / should exist early)

These files are the basic “starting kit” for a public GitHub project:

1. README.md

   * What it is:
     A human-facing explanation of what the project does.
   * Why it exists:
     GitHub viewers and employers usually read this first.
   * What it should contain:

     * What the tool does (in one or two sentences)
     * What problem it solves
     * How to run it (even if minimal)
     * The status (e.g., "work in progress")

2. LICENSE

   * What it is:
     A legal permission file (MIT License).
   * Why it exists:
     Without a license, other people technically have no permission to use
     the code. The MIT license makes it clear others can use the code while
     protecting the author from liability.
   * Important detail:
     MIT requires that the license text and copyright notice remain included
     when the code is redistributed.

3. .gitignore

   * What it is:
     A list of files/folders Git should NOT commit.
   * Why it exists:
     This project deals with potentially private ChatGPT exports. The .gitignore
     protects privacy and keeps the repo clean.
   * What it typically ignores:

     * Real exports like *.json and *.zip (private data)
     * Generated output folders (reproducible files)
     * Python caches and virtual environments (machine-specific junk)

4. convert.py

   * What it is:
     The main “entry point” script that a user runs.
   * Why it exists:
     It provides a single obvious command to run the tool.
   * What it should do (in the final design):

     * Read command-line options (input file, output format, output folder)
     * Call the parser (to read the export)
     * Call a renderer (to create output files)
     * Print a helpful summary or report

5. examples/conversations_fake.json

   * What it is:
     A fake, safe-to-share JSON export file.
   * Why it exists:
     The repo is public and should never include real personal conversation
     data. The fake example file allows testing and demonstration.
   * What it should include:

     * Multiple conversations
     * At least one “project” conversation
     * A few back-and-forth turns
     * At least one case with multiple assistant answers (“alternates”)

## Next needed files (minimum viable “real tool” structure)

The following additions create a clean architecture without being complicated.

## A) model.py (the internal data structures)

Filename:
model.py

What it does:

* Defines the project’s “neutral” internal representation of a conversation.
* This is the shape that the parser outputs and renderers consume.

Why it exists:

* Without a model, the parsing code and output code often get tangled together.
* A model makes it easy to add new output formats later without rewriting
  parsing logic.

What it typically contains (conceptually):

* Conversation:

  * id
  * title
  * timestamps
  * optional project metadata (if present)
  * a list of turns/messages
* Turn:

  * a user message
  * the main assistant response
  * optional alternate assistant responses
* Message:

  * role (user/assistant/system/tool)
  * text content (or a placeholder for non-text content)
  * timestamp if available

Important outcome:

* Once the internal model exists, renderers do not need to know anything about
  raw JSON. They only need to know how to output the model.

## B) parser.py (export JSON -> internal model)

Filename:
parser.py

What it does:

* Reads the official ChatGPT export file (conversations.json).
* Extracts conversations, messages, and metadata.
* Builds the model objects described in model.py.

Why it exists:

* Parsing JSON exports is the “messy” part. It should be isolated so it can
  be updated if the export schema changes.

Key tasks parser.py should handle:

1. Load the JSON file from disk.
2. For each conversation:

   * Read title and timestamps if present
   * Detect project metadata if present and store it in the model
3. Walk the conversation “mapping”:

   * ChatGPT exports often store messages in a tree-like structure, not a simple
     list. The parser needs to find a readable order.
4. Handle multiple assistant answers:

   * When the user regenerates an answer, the export may store multiple sibling
     assistant messages.
   * The parser should keep them as alternates, not discard them.
5. Handle non-text content:

   * If a message is tool output or attachment-like, the parser should insert a
     readable placeholder instead of crashing.

Important outcome:

* parser.py should create a complete model of each conversation that includes
  alternates and metadata, ready for any output format.

## C) renderers/ (folder for output formats)

Folder:
renderers/

What it does:

* Contains one file per output format.
* Each renderer takes the internal model and writes a transcript in a specific
  format.

Why it exists:

* This keeps output formatting separate from parsing logic.
* Adding a new format becomes “add a new renderer file,” not “rewrite the tool.”

Recommended minimum files inside renderers/:

1. renderers/**init**.py

   * What it does:
     Marks the folder as importable code and can define shared helpers.
   * Why it exists:
     Helps keep the structure clean and standard.

2. renderers/text.py

   * What it does:
     Writes plain .txt transcripts.
   * Why it exists:
     TXT is universally readable and is a good first output target.

3. renderers/markdown.py

   * What it does:
     Writes .md transcripts.
   * Why it exists:
     Markdown is human-friendly, previewable in VS Code, and easy to convert to
     HTML/PDF/DOCX later.

Later renderers (not needed at first, but planned):

* renderers/html.py
* renderers/docx.py
* renderers/pdf.py

Important outcome:

* Renderers should not parse JSON.
* Renderers should only deal with the clean model objects.

## D) convert.py (the orchestrator / runner script)

Filename:
convert.py

What it should become (after adding parser/model/renderers):

* A small coordinator, not a giant script.

What it does:

1. Reads command-line inputs, for example:

   * input JSON path
   * output folder
   * output format (txt, md, html, etc.)
2. Calls parser.py to build internal model objects.
3. Calls the chosen renderer to write transcripts.
4. Prints a summary and writes a small report if desired.

Why this matters:

* A small convert.py shows clean architecture.
* It demonstrates separation of concerns to reviewers.

## Final recommended structure (once the minimum is in place)

```text
chatgpt-data-export-parser/
├── README.md
├── LICENSE
├── .gitignore
├── convert.py
├── model.py
├── parser.py
├── renderers/
│   ├── __init__.py
│   ├── text.py
│   └── markdown.py
└── examples/
    └── conversations_fake.json
```


## Files deliberately NOT needed yet (avoid overengineering early)

These are useful later, but not required to start building a real tool:

* requirements.txt (not needed if there are no dependencies yet)
* packaging files beyond the basics (only needed if publishing to PyPI)
* CI workflows (nice later, not required for v1)
* tests/ directory (the examples JSON already provides a basic test input)
* docs site (can be added once the tool does something useful)

## Suggested next build order (simple progression)

1. Create model.py (define clean internal structures)
2. Create parser.py (read fake JSON and build model)
3. Create renderers/text.py (write readable .txt transcripts)
4. Create renderers/markdown.py (write readable .md transcripts)
5. Update convert.py to glue everything together with simple CLI arguments

## End of note
