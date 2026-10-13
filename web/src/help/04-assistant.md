# Assistant

Ask in plain English: *Which orders are late, and why?*, *What is short?*, *How is Gulf Fasteners doing?*,
*What is wrong with PO-0031?*

- The assistant reads only what your role can see, through the same tools the pages use. It cannot see the
  database or the internet.
- It cites what it used: click the order or item numbers in the answer.
- Every number must appear in the data it looked at. A sentence with a number it could not find is marked
  **unverified**.
- It can prepare drafts — a replenishment purchase order, a delay message to a customer, a nonconformance report.
  Drafts wait on the **Drafts** page for someone with the right role.
- Without an AI model key, built-in rules answer common questions. The owner adds the company's own Anthropic key
  to use Claude.

Every question and answer is kept with the steps the assistant took. Tell it whether an answer was useful.
