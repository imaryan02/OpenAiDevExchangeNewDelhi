# Docker Hub deployment

The workflow publishes the backend to public repository
`imaryan02/ai-receptionist-backend` with a commit SHA tag, then deploys its exact
digest to the existing Azure Container App. Existing environment variables and
quality/readiness checks are preserved.

Before running the workflow:

1. Create public Docker Hub repository `imaryan02/ai-receptionist-backend`.
2. Create a Docker Hub personal access token with Read & Write permission.
3. Save the token as GitHub repository Actions secret `DOCKERHUB_TOKEN`.

Keep the existing Azure OIDC secrets. The workflow no longer publishes to ACR.
Azure hosting charges still apply; retire ACR only after verifying that no
deployments or needed rollback images depend on it.

The friend's `akdevanurag/ai-receptionist-backend:v1` is not updated. After a
successful run, Azure should use the `imaryan02` image and serve the authenticated
Friday readiness route `/v1/personal-agent/readiness`.
