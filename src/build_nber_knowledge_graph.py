import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
FULL_INPUT_CSV = ROOT / "outputs" / "nber_environment_energy_structured.csv"
SAMPLE_INPUT_CSV = ROOT / "data" / "sample_papers.csv"
INPUT_CSV = FULL_INPUT_CSV if FULL_INPUT_CSV.exists() else SAMPLE_INPUT_CSV
OUTPUTS = ROOT / "outputs"

NODES_CSV = OUTPUTS / "nber_environment_energy_kg_nodes.csv"
EDGES_CSV = OUTPUTS / "nber_environment_energy_kg_edges.csv"
GRAPHML = OUTPUTS / "nber_environment_energy_kg.graphml"
METADATA_JSON = OUTPUTS / "nber_environment_energy_kg_metadata.json"


TOPIC_KEYWORDS = {
    "air_pollution": ["air pollution", "pm2.5", "particulate", "ozone", "pollution", "clean air"],
    "climate_policy": ["climate policy", "carbon tax", "carbon tariff", "cap-and-trade", "carbon price", "emissions"],
    "energy_markets": ["energy", "electricity", "natural gas", "oil", "fuel", "power", "grid"],
    "electric_vehicles": ["electric vehicle", "ev", "charging", "fuel economy", "battery"],
    "water": ["water", "drinking water", "flood", "flooding", "drought", "water rights"],
    "agriculture": ["agriculture", "farmer", "farm", "crop", "soil", "yield"],
    "deforestation_land_use": ["deforestation", "land use", "forest", "pasture", "agricultural frontier"],
    "natural_disasters": ["disaster", "wildfire", "hurricane", "storm", "heat", "blackout"],
    "health": ["health", "mortality", "stunting", "disease", "child nutrition", "exposure"],
    "housing_insurance": ["housing", "home insurance", "insurance", "mortgage", "home values", "flood risk"],
    "innovation_rd": ["innovation", "patent", "r&d", "research", "technology", "invention"],
    "sustainable_finance": ["sustainable investing", "green finance", "financial", "investment", "portfolio"],
    "trade_industrial_policy": ["trade", "tariff", "industrial policy", "subsidy", "competitiveness"],
    "environmental_justice": ["environmental justice", "exposure gap", "race", "ethnicity", "low-income"],
    "labor": ["labor", "employment", "wages", "workers", "mothers", "labor market"],
    "macroeconomics": ["macroeconomic", "macro", "gdp", "output", "inflation", "monetary"],
    "developing_economies": ["developing", "emerging", "emdes", "africa", "brazil", "china", "india"],
    "data_centers_ai": ["data center", "data centers", "ai", "artificial intelligence", "compute"],
    "biodiversity": ["biodiversity", "bird", "ecosystem", "nature", "natural capital"],
    "oil_gas": ["oil", "gas", "shale", "wells", "plugging", "fossil"],
    "public_opinion_behavior": ["survey", "support", "beliefs", "behavior", "preferences", "participation"],
}


METHOD_KEYWORDS = {
    "structural_model": ["structural model", "structural demand", "estimated model"],
    "general_equilibrium": ["general equilibrium", "equilibrium model", "dsge"],
    "difference_in_differences": ["difference-in-differences", "difference in differences", "did"],
    "event_study": ["event-study", "event study"],
    "randomized_experiment": ["randomized", "rct", "randomized controlled trial"],
    "field_experiment": ["field experiment", "natural field experiment"],
    "survey_experiment": ["survey experiment"],
    "instrumental_variables": ["instrument", "instrumental", "iv estimates"],
    "shift_share": ["shift-share", "shift share"],
    "satellite_data": ["satellite", "remote sensing"],
    "panel_data": ["panel", "longitudinal"],
    "machine_learning": ["machine learning", "ml"],
    "simulation": ["simulation", "simulations", "counterfactual"],
    "theoretical_model": ["theoretical model", "theory", "conceptual framework"],
}


DATA_KEYWORDS = {
    "administrative_data": ["administrative data", "administrative", "medicare", "census bureau"],
    "survey_data": ["survey", "household survey", "representative survey"],
    "satellite_data": ["satellite", "remote sensing", "vegetation indices"],
    "transaction_data": ["transaction", "transactions", "scanner data", "expenditure data"],
    "firm_data": ["firm", "firms", "firm-level"],
    "patent_data": ["patent", "patents"],
    "weather_climate_data": ["weather", "temperature", "heat", "climate"],
    "pollution_monitor_data": ["monitor", "monitors", "air quality", "pm2.5", "readings"],
    "property_housing_data": ["parcel", "mortgage", "property", "home insurance"],
    "energy_market_data": ["electricity market", "electricity prices", "natural gas", "oil prices"],
    "vehicle_data": ["vehicle-level", "vehicle", "ev trips", "charging events"],
    "geospatial_data": ["geolocated", "coordinates", "county", "commuting zone", "spatial"],
}


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def slug(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "unknown"


def node_id(node_type: str, label: str) -> str:
    return f"{node_type}:{slug(label)}"


def combined_text(row: dict) -> str:
    fields = [
        row.get("title", ""),
        row.get("research_question", ""),
        row.get("main_findings", ""),
        row.get("literature_value_added", ""),
        row.get("data_used", ""),
        row.get("method_or_design", ""),
    ]
    return " ".join(fields).lower()


def match_keywords(text: str, dictionary: dict[str, list[str]]) -> dict[str, list[str]]:
    matches = {}
    for key, keywords in dictionary.items():
        found = []
        for keyword in keywords:
            normalized = keyword.strip().lower()
            if len(normalized) <= 4 and re.fullmatch(r"[a-z0-9]+", normalized):
                is_match = re.search(rf"(?<!\w){re.escape(normalized)}(?!\w)", text) is not None
            else:
                is_match = normalized in text
            if is_match:
                found.append(keyword)
        if found:
            matches[key] = sorted(set(found))
    return matches


def add_node(nodes: dict[str, dict], node_id_value: str, label: str, node_type_value: str, **attrs) -> None:
    if node_id_value not in nodes:
        nodes[node_id_value] = {
            "id": node_id_value,
            "label": label,
            "type": node_type_value,
            **attrs,
        }
    else:
        nodes[node_id_value].update({k: v for k, v in attrs.items() if v})


def edge_key(source: str, target: str, edge_type: str) -> tuple[str, str, str]:
    return source, target, edge_type


def add_edge(
    edge_counts: Counter,
    edge_attrs: dict[tuple[str, str, str], dict],
    source: str,
    target: str,
    edge_type_value: str,
    **attrs,
) -> None:
    key = edge_key(source, target, edge_type_value)
    edge_counts[key] += 1
    existing = edge_attrs.setdefault(key, {})
    for attr_key, attr_value in attrs.items():
        if not attr_value:
            continue
        if attr_key in existing and existing[attr_key]:
            values = set(str(existing[attr_key]).split("; "))
            values.update(str(attr_value).split("; "))
            existing[attr_key] = "; ".join(sorted(values))
        else:
            existing[attr_key] = attr_value


def build_graph(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    nodes: dict[str, dict] = {}
    edge_counts: Counter = Counter()
    edge_attrs: dict[tuple[str, str, str], dict] = {}
    author_papers: defaultdict[str, list[str]] = defaultdict(list)

    for row in rows:
        paper_number = row.get("paper_number") or f"rank_{row.get('rank')}"
        paper_node = f"paper:{paper_number}"
        add_node(
            nodes,
            paper_node,
            row.get("title", paper_number),
            "paper",
            paper_number=paper_number,
            display_date=row.get("display_date", ""),
            publication_date=row.get("publication_date", ""),
            doi=row.get("doi", ""),
            url=row.get("url", ""),
            pdf_url=row.get("pdf_url", ""),
            abstract_word_count=row.get("abstract_word_count", ""),
        )

        authors = [author.strip() for author in row.get("authors", "").split(";") if author.strip()]
        for author in authors:
            author_node = node_id("author", author)
            add_node(nodes, author_node, author, "author")
            add_edge(edge_counts, edge_attrs, paper_node, author_node, "AUTHORED_BY")
            author_papers[author_node].append(paper_node)

        text = combined_text(row)

        for topic, matched_terms in match_keywords(text, TOPIC_KEYWORDS).items():
            topic_node = node_id("topic", topic)
            add_node(nodes, topic_node, topic.replace("_", " ").title(), "topic")
            add_edge(
                edge_counts,
                edge_attrs,
                paper_node,
                topic_node,
                "HAS_TOPIC",
                matched_terms="; ".join(matched_terms),
            )

        for method, matched_terms in match_keywords(text, METHOD_KEYWORDS).items():
            method_node = node_id("method", method)
            add_node(nodes, method_node, method.replace("_", " ").title(), "method")
            add_edge(
                edge_counts,
                edge_attrs,
                paper_node,
                method_node,
                "USES_METHOD",
                matched_terms="; ".join(matched_terms),
            )

        for data_signal, matched_terms in match_keywords(text, DATA_KEYWORDS).items():
            data_node = node_id("data", data_signal)
            add_node(nodes, data_node, data_signal.replace("_", " ").title(), "data_source")
            add_edge(
                edge_counts,
                edge_attrs,
                paper_node,
                data_node,
                "USES_DATA_SIGNAL",
                matched_terms="; ".join(matched_terms),
            )

    for author_node, papers in author_papers.items():
        if len(papers) < 2:
            continue
        for i, source in enumerate(papers):
            for target in papers[i + 1 :]:
                add_edge(edge_counts, edge_attrs, source, target, "SHARES_AUTHOR_WITH", shared_author=author_node)

    edge_rows = []
    for index, ((source, target, edge_type_value), weight) in enumerate(edge_counts.items(), start=1):
        attrs = edge_attrs.get((source, target, edge_type_value), {})
        edge_rows.append(
            {
                "id": f"edge_{index}",
                "source": source,
                "target": target,
                "type": edge_type_value,
                "weight": weight,
                "matched_terms": attrs.get("matched_terms", ""),
                "shared_author": attrs.get("shared_author", ""),
            }
        )

    return list(nodes.values()), edge_rows


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_graphml(path: Path, nodes: list[dict], edges: list[dict]) -> None:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
        '  <key id="label" for="node" attr.name="label" attr.type="string"/>',
        '  <key id="type" for="node" attr.name="type" attr.type="string"/>',
        '  <key id="url" for="node" attr.name="url" attr.type="string"/>',
        '  <key id="edge_type" for="edge" attr.name="type" attr.type="string"/>',
        '  <key id="weight" for="edge" attr.name="weight" attr.type="double"/>',
        '  <key id="matched_terms" for="edge" attr.name="matched_terms" attr.type="string"/>',
        '  <graph id="nber_environment_energy_kg" edgedefault="directed">',
    ]

    for node in nodes:
        lines.append(f'    <node id="{escape(node["id"])}">')
        lines.append(f'      <data key="label">{escape(str(node.get("label", "")))}</data>')
        lines.append(f'      <data key="type">{escape(str(node.get("type", "")))}</data>')
        lines.append(f'      <data key="url">{escape(str(node.get("url", "")))}</data>')
        lines.append("    </node>")

    for edge in edges:
        lines.append(
            f'    <edge id="{escape(edge["id"])}" source="{escape(edge["source"])}" '
            f'target="{escape(edge["target"])}">'
        )
        lines.append(f'      <data key="edge_type">{escape(str(edge.get("type", "")))}</data>')
        lines.append(f'      <data key="weight">{escape(str(edge.get("weight", "")))}</data>')
        lines.append(f'      <data key="matched_terms">{escape(str(edge.get("matched_terms", "")))}</data>')
        lines.append("    </edge>")

    lines.extend(["  </graph>", "</graphml>"])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    rows = read_rows(INPUT_CSV)
    nodes, edges = build_graph(rows)

    write_csv(
        NODES_CSV,
        nodes,
        [
            "id",
            "label",
            "type",
            "paper_number",
            "display_date",
            "publication_date",
            "doi",
            "url",
            "pdf_url",
            "abstract_word_count",
        ],
    )
    write_csv(
        EDGES_CSV,
        edges,
        ["id", "source", "target", "type", "weight", "matched_terms", "shared_author"],
    )
    write_graphml(GRAPHML, nodes, edges)

    metadata = {
        "input_rows": len(rows),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "node_types": Counter(node["type"] for node in nodes),
        "edge_types": Counter(edge["type"] for edge in edges),
        "outputs": {
            "nodes_csv": str(NODES_CSV),
            "edges_csv": str(EDGES_CSV),
            "graphml": str(GRAPHML),
        },
    }
    METADATA_JSON.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Input papers: {len(rows)}")
    print(f"Nodes: {len(nodes)}")
    print(f"Edges: {len(edges)}")
    print(f"Wrote {NODES_CSV}")
    print(f"Wrote {EDGES_CSV}")
    print(f"Wrote {GRAPHML}")


if __name__ == "__main__":
    main()
