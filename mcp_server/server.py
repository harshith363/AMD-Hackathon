"""Mock MCP-style catalogue server facade.

The hackathon app keeps the catalogue local, while the client functions mimic
the boundary a real MCP server would expose.
"""

from mcp_server.client import get_business_insurance_schemes, get_claim_compliance_rules, get_individual_insurance_schemes

__all__ = ["get_business_insurance_schemes", "get_claim_compliance_rules", "get_individual_insurance_schemes"]
