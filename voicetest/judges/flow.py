"""Flow judge for validating node traversal."""

from voicetest.models.test_case import TestCase


class FlowJudge:
    """Validate node traversal against constraints.

    Checks that required nodes were visited and forbidden
    nodes were avoided during the conversation.
    """

    def validate(
        self,
        nodes_visited: list[str],
        test_case: TestCase,
    ) -> list[str]:
        """Validate node traversal against test case constraints.

        Args:
            nodes_visited: List of node IDs visited during conversation.
            test_case: Test case with required/forbidden node constraints.

        Returns:
            List of violation messages (empty if all constraints met).
        """
        violations = []

        # Check required nodes
        if test_case.required_nodes:
            for required in test_case.required_nodes:
                if required not in nodes_visited:
                    violations.append(
                        f"Required node '{required}' was not visited"
                    )

        # Check forbidden nodes
        if test_case.forbidden_nodes:
            for forbidden in test_case.forbidden_nodes:
                if forbidden in nodes_visited:
                    violations.append(
                        f"Forbidden node '{forbidden}' was visited"
                    )

        return violations
