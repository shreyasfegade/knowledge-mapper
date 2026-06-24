"""Generate the bundled example graphs.

Runs the full Knowledge Mapper pipeline on a few hand-written educational texts
and writes each result to ``app/examples/<slug>.json``. Those files are seeded
into the database on startup (see ``app.examples_seed``) so the deployed demo
shows instant, zero-key example graphs.

Requires a working ``DEEPSEEK_API_KEY`` in the environment / backend/.env.

    cd backend
    python scripts/generate_examples.py            # all examples
    python scripts/generate_examples.py neural-networks   # one by slug
"""

import asyncio
import json
import os
import sys
import tempfile
import time

# Make the backend package importable when run as `python scripts/generate_examples.py`.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from reportlab.lib.pagesizes import letter  # noqa: E402
from reportlab.lib.styles import getSampleStyleSheet  # noqa: E402
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer  # noqa: E402

EXAMPLES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "app", "examples")
)

NEURAL_NETWORKS = """Introduction to Neural Networks

A neural network is a computational model loosely inspired by the structure of the biological brain. At its core sits the artificial neuron, a unit that takes several numeric inputs, multiplies each by a weight, sums them, adds a bias, and passes the result through an activation function. The weights and bias are the learnable parameters of the neuron.

The activation function is what gives a network its ability to model non-linear relationships. Without a non-linear activation, a stack of neurons would collapse into a single linear transformation, no matter how many layers it had. Common activation functions include the sigmoid, the hyperbolic tangent, and the rectified linear unit (ReLU). ReLU is popular because it is cheap to compute and mitigates the vanishing gradient problem.

Neurons are organised into layers. The input layer receives the raw features, one or more hidden layers transform the representation, and the output layer produces the prediction. A network with two or more hidden layers is called a deep network, which is where the term deep learning comes from. Connecting every neuron in one layer to every neuron in the next produces a fully connected, or dense, layer.

To train a network we need a way to measure how wrong its predictions are. This is the role of the loss function. For regression we often use mean squared error; for classification we use cross-entropy loss. The loss function depends on both the network's parameters and the training data.

Training is the process of adjusting the weights and biases to reduce the loss. The central algorithm is gradient descent. Gradient descent computes the gradient of the loss with respect to every parameter and nudges each parameter a small step in the direction that decreases the loss. The size of that step is controlled by the learning rate, a critical hyperparameter: too large and training diverges, too small and it crawls.

Computing the gradient efficiently in a deep network is done by backpropagation. Backpropagation applies the chain rule of calculus to propagate the error signal backwards from the output layer to the input layer, reusing intermediate results so that the gradient for every parameter is obtained in a single backward pass. Backpropagation therefore depends on the chain rule and produces the gradients that gradient descent consumes.

In practice we rarely compute the gradient over the entire dataset at once. Instead we use stochastic gradient descent, which estimates the gradient from a small random batch of examples. This makes each update cheaper and adds a useful amount of noise that can help escape poor local minima. Modern optimisers such as Adam build on stochastic gradient descent by adapting the learning rate per parameter using running estimates of the gradient.

A recurring danger is overfitting, where the network memorises the training data and fails to generalise to new examples. Regularisation techniques combat overfitting. Dropout randomly disables a fraction of neurons during training, forcing the network to build redundant representations. Weight decay penalises large weights in the loss function. Together these techniques improve generalisation, the ultimate goal of training.
"""

PHOTOSYNTHESIS = """Photosynthesis and Cellular Respiration

Photosynthesis is the process by which plants, algae, and some bacteria convert light energy into chemical energy stored in sugars. It is the foundation of nearly every food chain on Earth and the source of the oxygen in our atmosphere. The overall reaction takes carbon dioxide and water and, using light, produces glucose and oxygen.

The process happens inside the chloroplast, an organelle packed with the green pigment chlorophyll. Chlorophyll absorbs light most strongly in the blue and red parts of the spectrum and reflects green, which is why leaves appear green. The chloroplast contains stacked membranes called thylakoids and a surrounding fluid called the stroma.

Photosynthesis proceeds in two connected stages. The first stage is the light-dependent reactions, which occur in the thylakoid membranes. Here, absorbed light excites electrons in chlorophyll, splitting water molecules to release oxygen and producing two energy carriers: ATP and NADPH. The light-dependent reactions therefore depend on light and on water as an electron source.

The second stage is the Calvin cycle, also called the light-independent reactions, which takes place in the stroma. The Calvin cycle uses the ATP and NADPH produced by the light-dependent reactions to fix carbon dioxide into glucose. Because it consumes the products of the first stage, the Calvin cycle depends on the light-dependent reactions, even though it does not directly require light.

The glucose produced by photosynthesis is more than food; it is stored chemical energy. To release that energy, cells perform cellular respiration, in essence the reverse transformation. Cellular respiration breaks down glucose using oxygen to produce ATP, the universal energy currency of the cell, releasing carbon dioxide and water as by-products.

Cellular respiration occurs largely in the mitochondrion and unfolds in three steps. Glycolysis splits glucose into two molecules of pyruvate in the cytoplasm, yielding a small amount of ATP. The pyruvate then enters the citric acid cycle, also known as the Krebs cycle, which strips electrons from the carbon compounds and captures them on carrier molecules. Finally, the electron transport chain uses those high-energy electrons to drive the bulk production of ATP.

The two processes form an elegant cycle that links all life. Photosynthesis consumes carbon dioxide and water and produces glucose and oxygen; cellular respiration consumes glucose and oxygen and produces carbon dioxide and water. The oxygen released by photosynthesis enables respiration, and the carbon dioxide released by respiration feeds photosynthesis. ATP produced in both pathways powers the work of the cell, from building proteins to moving molecules across membranes.
"""

SUPPLY_DEMAND = """Supply, Demand, and Market Equilibrium

Economics studies how people allocate scarce resources, and few ideas are as central as supply and demand. Together they explain how prices form in a market and why they change. A market is any arrangement that brings buyers and sellers of a good together.

Demand describes the relationship between the price of a good and the quantity that buyers are willing and able to purchase. The law of demand states that, all else equal, as the price rises the quantity demanded falls, and as the price falls the quantity demanded rises. Plotted on a graph, this inverse relationship produces the downward-sloping demand curve.

Demand depends on more than price. Shifts in the entire demand curve are caused by changes in income, the prices of related goods, consumer tastes, and expectations about the future. A rise in income, for example, increases demand for most goods, shifting the demand curve to the right.

Supply describes the relationship between the price of a good and the quantity that sellers are willing to produce. The law of supply states that, all else equal, a higher price increases the quantity supplied, because higher prices make production more profitable. This produces the upward-sloping supply curve. Like demand, supply shifts in response to other factors, especially the cost of inputs and the state of technology. Better technology lowers production costs and shifts supply to the right.

The interaction of supply and demand determines the market price. Market equilibrium is the price at which the quantity demanded exactly equals the quantity supplied. At this equilibrium price the market clears, leaving neither a shortage nor a surplus. Equilibrium therefore depends on both the supply curve and the demand curve.

When the price sits above equilibrium, the quantity supplied exceeds the quantity demanded, producing a surplus. Sellers respond by cutting prices, pushing the market back toward equilibrium. When the price sits below equilibrium, the quantity demanded exceeds the quantity supplied, producing a shortage, and competition among buyers drives the price up. This self-correcting behaviour is what economists call the price mechanism.

Because price guides the decisions of millions of independent buyers and sellers, it acts as a signal that coordinates economic activity without any central planner. A rise in the equilibrium price tells producers to make more and consumers to buy less; a fall does the opposite. Understanding how shifts in supply and demand move the equilibrium is the key to predicting how events ripple through a market.
"""

EXAMPLES = [
    {
        "slug": "neural-networks",
        "title": "Introduction to Neural Networks",
        "filename": "Introduction to Neural Networks.pdf",
        "text": NEURAL_NETWORKS,
    },
    {
        "slug": "photosynthesis",
        "title": "Photosynthesis & Cellular Respiration",
        "filename": "Photosynthesis and Cellular Respiration.pdf",
        "text": PHOTOSYNTHESIS,
    },
    {
        "slug": "supply-and-demand",
        "title": "Supply, Demand & Market Equilibrium",
        "filename": "Supply, Demand and Market Equilibrium.pdf",
        "text": SUPPLY_DEMAND,
    },
]


def _build_pdf(text: str, path: str) -> None:
    doc = SimpleDocTemplate(path, pagesize=letter)
    styles = getSampleStyleSheet()
    flow = []
    for block in text.strip().split("\n\n"):
        flow.append(Paragraph(block.replace("\n", " "), styles["Normal"]))
        flow.append(Spacer(1, 10))
    doc.build(flow)


async def _generate_one(ex: dict) -> None:
    from app.services.text_extractor import extract_text
    from app.services.text_cleaner import clean_text
    from app.services.global_understanding import async_extract_global_understanding
    from app.services.concept_extractor import async_extract_concepts
    from app.services.hierarchy_assembly import assemble_hierarchy
    from app.services.topology_inference import async_assemble_topology
    from app.services.graph_transformer import transform_graph
    from app.config import MAX_RESPONSE_TEXT_CHARS

    slug = ex["slug"]
    print(f"\n=== {slug} ===", flush=True)
    t0 = time.monotonic()

    pdf_path = os.path.join(tempfile.gettempdir(), f"{slug}.pdf")
    _build_pdf(ex["text"], pdf_path)
    cleaned = clean_text(extract_text(pdf_path))

    gu = await async_extract_global_understanding(cleaned)
    raw_concepts = await async_extract_concepts(cleaned, global_understanding=gu)
    concepts = assemble_hierarchy(raw_concepts)
    relationships, hubs = await async_assemble_topology(concepts, global_understanding=gu)
    graph = transform_graph(concepts, relationships, hubs)

    text_truncated = len(cleaned) > MAX_RESPONSE_TEXT_CHARS
    result = {
        "document_id": f"example-{slug}",
        "filename": ex["filename"],
        "char_count": len(cleaned),
        "text": cleaned[:MAX_RESPONSE_TEXT_CHARS] if text_truncated else cleaned,
        "text_truncated": text_truncated,
        "global_understanding": gu if isinstance(gu, dict) else {},
        "concepts": concepts,
        "relationships": relationships,
        "hub_concepts": hubs,
        "graph": graph,
        "is_example": True,
        "example_title": ex["title"],
    }

    os.makedirs(EXAMPLES_DIR, exist_ok=True)
    out = os.path.join(EXAMPLES_DIR, f"{slug}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(
        f"  saved {os.path.relpath(out)} — "
        f"{len(graph.get('nodes', []))} nodes, {len(graph.get('edges', []))} edges, "
        f"{len(hubs)} hubs in {time.monotonic() - t0:.0f}s",
        flush=True,
    )


async def main(slugs: list[str]) -> None:
    targets = [e for e in EXAMPLES if not slugs or e["slug"] in slugs]
    if not targets:
        print(f"No example matches {slugs}. Available: {[e['slug'] for e in EXAMPLES]}")
        sys.exit(1)
    for ex in targets:
        await _generate_one(ex)
    print(f"\nDone. Generated {len(targets)} example(s) into {os.path.relpath(EXAMPLES_DIR)}.")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
