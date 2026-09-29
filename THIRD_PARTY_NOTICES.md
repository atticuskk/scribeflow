# Third-Party Notices

The Git repository contains project source. Release ZIPs also contain a standalone
CPython 3.12 runtime and installed dependency distributions; no model weights are
bundled. Original distribution licenses remain in the runtime and are collected
in Contents/Resources/Licenses with a machine-readable index.json. The CPython
license and this project's MIT license are included there as well.

| Component | Use in this project | License | Source |
| --- | --- | --- | --- |
| MinerU 3.4.4 (optional `ocr` extra; bundled in the app) | Local OCR and layout analysis | MinerU Open Source License (Apache-2.0 with additional terms) | https://github.com/opendatalab/MinerU |
| OpenAI Python | Optional OpenAI-compatible AI cleaning client | Apache-2.0 | https://github.com/openai/openai-python |
| pypdf | PDF page inspection and splitting | BSD-3-Clause | https://github.com/py-pdf/pypdf |

## MinerU notice

MinerU is distributed under Apache License 2.0 with additional terms. It may
be used commercially without a separate commercial license unless the user and
its affiliates exceed MinerU's stated MAU or monthly-revenue thresholds. A
third-party online service based on MinerU must clearly and prominently state
in its interface or public documentation that it uses MinerU. See the current
license text at https://github.com/opendatalab/MinerU/blob/master/LICENSE.md.

The dependency versions resolved for this release are recorded in `uv.lock`.
This notice is informational and does not replace the upstream license texts.
