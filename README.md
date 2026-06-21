# NBER Environment and Energy Economics Knowledge Graph

An educational Python workflow for collecting NBER Environment and Energy Economics working-paper metadata, creating structured notes from paper abstracts, and building a typed knowledge graph.

The repository contains a standard-library data pipeline, a graph builder, a Markdown tutorial, a Jupyter notebook, and a small sample dataset that runs without downloading the full corpus.

## Repository Layout

```text
data/
  sample_papers.csv
  README.md
notebooks/
  nber_knowledge_graph_tutorial.ipynb
outputs/
  .gitkeep
src/
  build_nber_knowledge_graph.py
  fetch_structured_nber_environment_energy.py
tests/
  test_smoke.py
tutorials/
  nber_environment_energy_python_tutorial.md
LICENSE
README.md
requirements.txt
```

## Quick Start

Python 3.10 or newer is recommended.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Build a knowledge graph from the included 40-paper sample:

```powershell
python src\build_nber_knowledge_graph.py
```

Generated files are written to `outputs/`:

- `nber_environment_energy_kg_nodes.csv`
- `nber_environment_energy_kg_edges.csv`
- `nber_environment_energy_kg.graphml`
- `nber_environment_energy_kg_metadata.json`

## Jupyter Notebook

Launch Jupyter from the repository root:

```powershell
jupyter lab
```

Then open `notebooks/nber_knowledge_graph_tutorial.ipynb` and run the cells from top to bottom. The notebook uses the full generated dataset when present and otherwise falls back to `data/sample_papers.csv`.

## Fetch the Current NBER Listing

The following command queries the NBER listing endpoint and individual paper pages:

```powershell
python src\fetch_structured_nber_environment_energy.py
```

This is a network operation and can take several minutes. Keep request rates reasonable and review NBER's current website terms before running or publishing derived outputs. The NBER endpoint and page markup are external interfaces and may change.

The fetcher creates structured, nonverbatim notes rather than redistributing full abstracts. It writes the full structured dataset to `outputs/nber_environment_energy_structured.csv` along with JSON and Markdown versions. The graph builder automatically prefers that file over the sample dataset.

## Knowledge Graph Schema

Node types:

- `paper`
- `author`
- `topic`
- `method`
- `data_source`

Edge types:

- `AUTHORED_BY`
- `HAS_TOPIC`
- `USES_METHOD`
- `USES_DATA_SIGNAL`
- `SHARES_AUTHOR_WITH`

The keyword taxonomy is intentionally transparent and editable in `src/build_nber_knowledge_graph.py`. It is a teaching baseline, not a validated scholarly classification system.

## Tests

Run the offline smoke test:

```powershell
python -m unittest discover -s tests
```

## Tutorials

- [`tutorials/nber_environment_energy_python_tutorial.md`](tutorials/nber_environment_energy_python_tutorial.md): end-to-end data collection and structuring walkthrough.
- [`notebooks/nber_knowledge_graph_tutorial.ipynb`](notebooks/nber_knowledge_graph_tutorial.ipynb): executable knowledge-graph tutorial with an optional NetworkX and Plotly 3D preview.

## Data and Copyright

The repository does not grant rights to NBER papers, abstracts, PDFs, or third-party metadata. Those materials remain subject to their respective owners' terms. The included sample contains bibliographic metadata, source links, and short structured notes created for demonstration. Follow the NBER links to consult original paper pages.

## License

Original code and documentation in this repository are available under the MIT License. See [`LICENSE`](LICENSE).
