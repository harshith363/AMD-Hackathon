from __future__ import annotations

from mcp_server.client import get_business_insurance_schemes, get_individual_insurance_schemes
from orchestrator.trace import WorkflowTrace
from schemas.messages import ProductDiscoveryMessage, ProductRecommendationMessage


class ProductDiscoveryAgent:
    name = "Product Discovery Agent"

    def recommend(self, message: ProductDiscoveryMessage, trace: WorkflowTrace) -> ProductRecommendationMessage:
        if message.customer_type == "business":
            recommendations = get_business_insurance_schemes(message.insurance_category, message.user_inputs)
        else:
            recommendations = get_individual_insurance_schemes(message.insurance_category, message.user_inputs)
        trace.add(self.name, "called_mock_mcp_catalogue", {"category": message.insurance_category, "count": len(recommendations)})
        return ProductRecommendationMessage(
            session_id=message.session_id,
            customer_type=message.customer_type,
            insurance_category=message.insurance_category,
            user_inputs=message.user_inputs,
            recommendations=recommendations,
        )
