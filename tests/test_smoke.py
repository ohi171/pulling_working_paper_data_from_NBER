import sys
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import build_nber_knowledge_graph as kg


class KnowledgeGraphSmokeTest(unittest.TestCase):
    def test_sample_builds_typed_graph(self):
        rows = kg.read_rows(ROOT / "data" / "sample_papers.csv")
        nodes, edges = kg.build_graph(rows)

        self.assertEqual(len(rows), 40)
        self.assertEqual(sum(node["type"] == "paper" for node in nodes), 40)
        self.assertGreater(len(nodes), 40)
        self.assertGreater(len(edges), 0)

        node_types = Counter(node["type"] for node in nodes)
        edge_types = Counter(edge["type"] for edge in edges)
        self.assertIn("author", node_types)
        self.assertIn("topic", node_types)
        self.assertIn("AUTHORED_BY", edge_types)
        self.assertIn("HAS_TOPIC", edge_types)


if __name__ == "__main__":
    unittest.main()
