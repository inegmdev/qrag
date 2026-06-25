## Ugly TUI

Current TUI is really ugly and is not 2026ish, please update it and make the progress bars for every thing, add ETA and also make sure you report when qrag prepare

## Keep Track of the prepared files

Always keep a text file for the prepare files as a report after the database is done, this will allow the user to understand what has been added in the database and what is not, what is detected as a C what is detected as a Makefile, ..etc. Also the time taken for jobs and the total time of the operations.

## Ability to search across all the databases

Now the qrag have the feature of one database and this is fine, but in qrag ecosystem I want the user to be able to prepare as much as databases he can from (code and docs) and being able to use /qrag to find the good data from multiple databases, this will mean that qrag will need to search across all the databases and use the highest based databases feeding the LLM, I think we need to check if the current structure is quick if the user have for example 100 database ranging in 400MB of data, what is the quickest way to search this huge number?

## Section, page, subsection in the feature tags for RAG entries for documents

Currently the implemented does not have these metadata, and thus when I ask the LLM about the referneces it struggles regarding it.

In the feature tags for the documents I need.

1. Name of the document.
2. Revision of the document.
3. Status of the document (if found, like draft, revised, released, ..etc)
4. Page number or range.
5. Section number and name, also subsections to the paragraph level.
6. Please suggest one me any other meta data that can be parsed and stored in each chunk.

## File name and path, line number, parent function or class in the feature tags for RAG entries for code

Same as the above one for documents but for code, the goal is to allow the LLM to reference the parts and give the user ability to double confirm.

In the feature tags for the code I need:

1. File path
2. File name.
3. Line number range.
4. parent block name (function, class, array, ..etc).
5. Please suggest one me any other meta data that can be parsed and stored in each chunk.
