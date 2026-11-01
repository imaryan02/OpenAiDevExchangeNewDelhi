"""Discover Sarvam Voice Agent deployment values without printing credentials."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from app.core.config import Settings


def update_env(values: dict[str, str]) -> None:
    path = Path(__file__).resolve().parents[1] / ".env"
    lines = path.read_text(encoding="utf-8").splitlines()
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in values:
            output.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            output.append(line)
    output.extend(f"{key}={value}" for key, value in values.items() if key not in seen)
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


def main() -> int:
    settings = Settings()
    if not settings.sarvam_voice_api_key:
        raise SystemExit("SARVAM_VOICE_API_KEY is missing.")
    if not settings.sarvam_organization_id or not settings.sarvam_workspace_id:
        raise SystemExit("Sarvam organization/workspace IDs are missing.")

    base = "https://apps.sarvam.ai/api/app-authoring/v1"
    path = (
        f"/orgs/{settings.sarvam_organization_id}"
        f"/workspaces/{settings.sarvam_workspace_id}/deployments"
    )
    response = httpx.get(
        f"{base}{path}",
        headers={"X-API-Key": settings.sarvam_voice_api_key},
        params={"limit": 100},
        timeout=30,
    )
    if response.status_code >= 400:
        print(json.dumps({"status": response.status_code, "error": response.text[:500]}))
        return 1

    items = response.json().get("items", [])
    phone = settings.sarvam_phone_number or "+917965853965"
    matches = [item for item in items if phone in item.get("phone_numbers", [])]
    if not matches:
        print(
            json.dumps(
                {
                    "deployments_found": len(items),
                    "phone": phone,
                    "matching_deployment": False,
                }
            )
        )
        update_env({"SARVAM_PHONE_NUMBER": phone})
        return 2

    selected = matches[0]
    deployment_id = str(selected["deployment_id"])
    detail = httpx.get(
        f"{base}{path}/{deployment_id}",
        headers={"X-API-Key": settings.sarvam_voice_api_key},
        timeout=30,
    )
    detail.raise_for_status()
    deployment = detail.json()
    connection_configs = deployment.get("connection_configs", [])
    connection = next(
        (item for item in connection_configs if phone in item.get("phone_numbers", [])),
        None,
    )
    values = {
        "SARVAM_AGENT_ID": str(deployment["app_id"]),
        "SARVAM_AGENT_VERSION": str(deployment["app_version"]),
        "SARVAM_PHONE_NUMBER": phone,
    }
    if connection and connection.get("connection_id"):
        values["SARVAM_CONNECTION_ID"] = str(connection["connection_id"])
    update_env(values)
    print(
        json.dumps(
            {
                "matching_deployment": True,
                "deployment_id": deployment_id,
                "agent_id": values["SARVAM_AGENT_ID"],
                "agent_version": values["SARVAM_AGENT_VERSION"],
                "connection_id_found": "SARVAM_CONNECTION_ID" in values,
                "phone": phone,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
