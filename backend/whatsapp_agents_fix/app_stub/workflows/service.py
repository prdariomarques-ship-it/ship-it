class _FakeWorkflowService:
    async def trigger(self, *args, **kwargs):
        raise NotImplementedError("workflow_service is not exercised by this test suite")


workflow_service = _FakeWorkflowService()
