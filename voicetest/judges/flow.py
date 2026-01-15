"""Flow judge for validating node traversal."""


class FlowJudge:
    """Validate node traversal.

    Placeholder for future flow constraint validation.
    Currently returns no violations.
    """

    def validate(
        self,
        nodes_visited: list[str],
    ) -> list[str]:
        """Validate node traversal.

        Args:
            nodes_visited: List of node IDs visited during conversation.

        Returns:
            List of violation messages (currently always empty).
        """
        return []
