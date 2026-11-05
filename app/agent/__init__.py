"""Agent runtime: a bounded tool-calling loop around a swappable model provider.

The model only ever PROPOSES tool calls. Every proposal is executed through
app.gateway.execute_tool with the trusted Principal from the HTTP identity layer.
"""
