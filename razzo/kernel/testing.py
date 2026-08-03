from __future__ import annotations

from .capability import CapabilityNode, CapabilitySpec, HomoLevel, compile_capability

SHA = "a" * 40
A1 = "The operator can list expiring batches by date."
A2 = "The operator can export the filtered result."
A3 = "Invalid expiry dates are rejected with a useful error."


def make_spec(*, sha: str = SHA):
    return CapabilitySpec(
        project_id="pfarma-cloud",
        title="Inventory expiry management",
        user_outcome="The operator can inspect and export expiring inventory safely.",
        exact_base_sha=sha,
        acceptance_criteria=(A1, A2, A3),
        collision_domains=(
            "inventory/schema",
            "inventory/query",
            "inventory/export",
            "inventory/ui",
            "inventory/qa",
        ),
    )


def make_nodes():
    return (
        CapabilityNode(
            node_id="N001",
            title="Expiry persistence contract",
            level=HomoLevel.CELL,
            responsibility="Add and validate the expiry persistence contract.",
            dependencies=(),
            allowed_surfaces=("inventory/models/expiry.py", "tests/inventory/test_expiry_model.py"),
            acceptance_subset=(A3,),
            collision_domain="inventory/schema",
            verification=("python -m unittest tests.inventory.test_expiry_model",),
            priority=100,
            product_value=80,
            unlock_value=100,
            parallel_value=70,
            risk=30,
            estimated_cost=2,
        ),
        CapabilityNode(
            node_id="N002",
            title="Expiry query",
            level=HomoLevel.CELL,
            responsibility="Implement the bounded query for expiring batches.",
            dependencies=("N001",),
            allowed_surfaces=("inventory/services/expiry.py", "tests/inventory/test_expiry_query.py"),
            acceptance_subset=(A1,),
            collision_domain="inventory/query",
            verification=("python -m unittest tests.inventory.test_expiry_query",),
            priority=95,
            product_value=100,
            unlock_value=90,
            parallel_value=80,
            risk=20,
            estimated_cost=2,
        ),
        CapabilityNode(
            node_id="N003",
            title="Expiry export",
            level=HomoLevel.CELL,
            responsibility="Export the current expiry result without changing its filters.",
            dependencies=("N002",),
            allowed_surfaces=("inventory/exports/expiry.py", "tests/inventory/test_expiry_export.py"),
            acceptance_subset=(A2,),
            collision_domain="inventory/export",
            verification=("python -m unittest tests.inventory.test_expiry_export",),
            priority=80,
            product_value=90,
            unlock_value=40,
            parallel_value=90,
            risk=20,
            estimated_cost=1,
        ),
        CapabilityNode(
            node_id="N004",
            title="Expiry user interface",
            level=HomoLevel.ORGAN,
            responsibility="Expose the query and export flow in the operator interface.",
            dependencies=("N002",),
            allowed_surfaces=("frontend/inventory/expiry/index.ts", "tests/browser/inventory_expiry.spec.ts"),
            acceptance_subset=(A1, A2),
            collision_domain="inventory/ui",
            verification=("npm test -- inventory_expiry",),
            priority=90,
            product_value=100,
            unlock_value=50,
            parallel_value=100,
            risk=25,
            estimated_cost=2,
        ),
        CapabilityNode(
            node_id="N005",
            title="Capability journey verification",
            level=HomoLevel.SYSTEM,
            responsibility="Verify the complete user-visible expiry journey.",
            dependencies=("N003", "N004"),
            allowed_surfaces=("tests/journeys/inventory_expiry.py",),
            acceptance_subset=(A1, A2, A3),
            collision_domain="inventory/qa",
            verification=("python tests/journeys/inventory_expiry.py",),
            priority=85,
            product_value=100,
            unlock_value=20,
            parallel_value=20,
            risk=10,
            estimated_cost=1,
        ),
    )


def make_plan(*, sha: str = SHA):
    return compile_capability(make_spec(sha=sha), make_nodes())
