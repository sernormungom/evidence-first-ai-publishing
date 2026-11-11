# Information and release policy

Public: reusable code, prompts, independently authored synthetic fixtures and documentation.
Private: original source documents, article text, reviewer identities, company decisions, source revision mapping, provider captures and run logs. Keep these outside this checkout.

Allowlist exports from committed code; never copy a working directory recursively. Start fresh history. Do not merge company history. Scan the staged tree, all new history and deployment artifact before public release. Secret scanning complements manual review; neither proves absence of confidential information.

Initial release: create a private personal repository, push only this history, inspect the committed tree and CI artifact, then change visibility to public and enable Pages. Tag v1.0.0 only after deployed links and both languages are verified. Use the GitHub noreply address for future commits.

The source revision and detailed export audit are deliberately stored outside the public repository.
