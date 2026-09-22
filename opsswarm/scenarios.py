from pathlib import Path
import yaml
P=Path(__file__).resolve().parent.parent/'experiments'/'scenarios.yaml'
def load(): return {x['id']:x for x in yaml.safe_load(P.read_text())['scenarios']}
