#!/usr/bin/env python3

# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
GDC Air-Gapped Platform Auditing & Security Compliance CLI Tool.

Queries and analyzes Kubernetes / GDC API server audit logs for:
- Privileged escalation & IAM modifications (ClusterRoleBindings, RoleBindings)
- Sensitive secret access & exfiltration attempts
- NetworkPolicy and security perimeter tampering
- Anonymous / Unauthorized 401/403 access attempts
- Interactive exec/attach sessions into tenant containers
"""

import argparse
import datetime
import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional


def generate_sample_audit_events() -> List[Dict[str, Any]]:
    """Generates realistic audit log events for air-gapped forensic demonstration."""
    base_time = datetime.datetime.now(datetime.timezone.utc)
    return [
        {
            "auditID": "gdc-aud-001",
            "stage": "ResponseComplete",
            "requestURI": "/apis/rbac.authorization.k8s.io/v1/clusterrolebindings",
            "verb": "create",
            "user": {"username": "contractor-dev@tenant-b.local", "groups": ["system:authenticated"]},
            "sourceIPs": ["192.168.1.105"],
            "userAgent": "kubectl/v1.28.0",
            "objectRef": {
                "resource": "clusterrolebindings",
                "name": "escalated-admin-binding",
                "apiGroup": "rbac.authorization.k8s.io",
                "apiVersion": "v1"
            },
            "responseStatus": {"metadata": {}, "code": 403, "reason": "Forbidden", "message": "clusterrolebindings.rbac.authorization.k8s.io is forbidden: User cannot create resource in the cluster scope"},
            "requestReceivedTimestamp": (base_time - datetime.timedelta(minutes=14)).isoformat()
        },
        {
            "auditID": "gdc-aud-002",
            "stage": "ResponseComplete",
            "requestURI": "/api/v1/namespaces/shared-services/secrets/db-root-credentials",
            "verb": "get",
            "user": {"username": "suspicious-service-account", "groups": ["system:serviceaccounts:tenant-b"]},
            "sourceIPs": ["10.200.4.12"],
            "userAgent": "curl/7.88.1",
            "objectRef": {
                "resource": "secrets",
                "namespace": "shared-services",
                "name": "db-root-credentials",
                "apiVersion": "v1"
            },
            "responseStatus": {"metadata": {}, "code": 403, "reason": "Forbidden"},
            "requestReceivedTimestamp": (base_time - datetime.timedelta(minutes=10)).isoformat()
        },
        {
            "auditID": "gdc-aud-003",
            "stage": "ResponseComplete",
            "requestURI": "/apis/networking.k8s.io/v1/namespaces/tenant-a/networkpolicies/default-deny-all-traffic",
            "verb": "delete",
            "user": {"username": "developer-user@tenant-a.local", "groups": ["system:authenticated"]},
            "sourceIPs": ["192.168.1.44"],
            "userAgent": "kubectl/v1.28.0",
            "objectRef": {
                "resource": "networkpolicies",
                "namespace": "tenant-a",
                "name": "default-deny-all-traffic",
                "apiGroup": "networking.k8s.io",
                "apiVersion": "v1"
            },
            "responseStatus": {"metadata": {}, "code": 403, "reason": "Forbidden", "message": "Only platform-admin may alter baseline security tier policies"},
            "requestReceivedTimestamp": (base_time - datetime.timedelta(minutes=6)).isoformat()
        },
        {
            "auditID": "gdc-aud-004",
            "stage": "ResponseComplete",
            "requestURI": "/api/v1/namespaces/frontend-project/pods/frontend-v1-7d889/exec",
            "verb": "create",
            "user": {"username": "platform-admin@gdc.local", "groups": ["system:masters", "platform-admins"]},
            "sourceIPs": ["192.168.1.10"],
            "userAgent": "kubectl/v1.28.0",
            "objectRef": {
                "resource": "pods",
                "subresource": "exec",
                "namespace": "frontend-project",
                "name": "frontend-v1-7d889",
                "apiVersion": "v1"
            },
            "responseStatus": {"metadata": {}, "code": 200},
            "requestReceivedTimestamp": (base_time - datetime.timedelta(minutes=3)).isoformat()
        },
        {
            "auditID": "gdc-aud-005",
            "stage": "ResponseComplete",
            "requestURI": "/apis/apps/v1/namespaces/backend-api-project/deployments/api-service",
            "verb": "patch",
            "user": {"username": "cicd-runner@system.gdc", "groups": ["system:authenticated"]},
            "sourceIPs": ["10.200.2.8"],
            "userAgent": "Go-http-client/1.1",
            "objectRef": {
                "resource": "deployments",
                "namespace": "backend-api-project",
                "name": "api-service",
                "apiGroup": "apps",
                "apiVersion": "v1"
            },
            "responseStatus": {"metadata": {}, "code": 200},
            "requestReceivedTimestamp": (base_time - datetime.timedelta(minutes=1)).isoformat()
        }
    ]


def classify_event_severity(event: Dict[str, Any]) -> tuple[str, str]:
    """Evaluates audit event for compliance violation risk and returns (severity, rule_name)."""
    obj_ref = event.get("objectRef", {})
    resource = obj_ref.get("resource", "")
    subresource = obj_ref.get("subresource", "")
    verb = event.get("verb", "").lower()
    status_code = event.get("responseStatus", {}).get("code", 200)
    user = event.get("user", {}).get("username", "unknown")

    # 1. Privilege Escalation Attempts
    if resource in ["clusterroles", "clusterrolebindings"] and verb in ["create", "update", "patch", "delete"]:
        if status_code in [401, 403]:
            return "HIGH", "UNAUTHORIZED_PRIVILEGE_ESCALATION_ATTEMPT"
        return "CRITICAL", "CLUSTER_PRIVILEGED_IAM_MUTATION"

    # 2. Secret exfiltration attempts
    if resource == "secrets":
        if status_code in [401, 403]:
            return "HIGH", "UNAUTHORIZED_SECRET_ACCESS_DENIED"
        if verb in ["get", "list"] and "system:serviceaccounts" in str(event.get("user", {}).get("groups", [])):
            return "MEDIUM", "SERVICE_ACCOUNT_SECRET_INSPECTION"

    # 3. Network Policy tampering
    if resource == "networkpolicies" and verb in ["delete", "patch", "update"]:
        if status_code in [401, 403]:
            return "HIGH", "UNAUTHORIZED_NETWORK_POLICY_TAMPERING"
        return "HIGH", "NETWORK_SECURITY_POLICY_MODIFIED"

    # 4. Interactive container access
    if resource == "pods" and subresource in ["exec", "attach", "portforward"]:
        return "MEDIUM", "INTERACTIVE_CONTAINER_EXECUTION"

    # 5. General unauthorized access
    if status_code in [401, 403]:
        return "LOW", "ACCESS_DENIED"

    return "INFO", "ROUTINE_API_OPERATION"


def query_live_cluster_events(kubeconfig: Optional[str] = None) -> List[Dict[str, Any]]:
    """Queries events from live Kubernetes API server as an audit proxy."""
    cmd = ["kubectl", "get", "events", "-A", "-o", "json"]
    if kubeconfig:
        cmd.extend(["--kubeconfig", kubeconfig])
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        raw_data = json.loads(res.stdout)
        events = []
        for item in raw_data.get("items", []):
            events.append({
                "auditID": item.get("metadata", {}).get("uid", "live-evt"),
                "stage": "ResponseComplete",
                "requestURI": f"/api/v1/namespaces/{item.get('involvedObject', {}).get('namespace', '')}/{item.get('involvedObject', {}).get('kind', '')}",
                "verb": item.get("reason", "Event").lower(),
                "user": {"username": item.get("reportingComponent", "kube-system")},
                "sourceIPs": ["cluster-internal"],
                "userAgent": item.get("source", {}).get("component", "k8s-engine"),
                "objectRef": {
                    "resource": item.get("involvedObject", {}).get("kind", "").lower() + "s",
                    "namespace": item.get("involvedObject", {}).get("namespace", ""),
                    "name": item.get("involvedObject", {}).get("name", "")
                },
                "responseStatus": {"code": 200 if item.get("type") == "Normal" else 400, "message": item.get("message", "")},
                "requestReceivedTimestamp": item.get("lastTimestamp") or item.get("eventTime") or datetime.datetime.now(datetime.timezone.utc).isoformat()
            })
        return events
    except Exception as e:
        print(f"[WARN] Unable to fetch live cluster events: {e}. Falling back to sample dataset.")
        return generate_sample_audit_events()


def main():
    parser = argparse.ArgumentParser(
        description="GDC Air-Gapped Platform Auditing & Security Compliance CLI Tool"
    )
    parser.add_argument("--log-file", type=str, help="Path to Kubernetes API audit JSON/JSONL log file")
    parser.add_argument("--live", action="store_true", help="Query live cluster API events")
    parser.add_argument("--kubeconfig", type=str, help="Custom kubeconfig path for live queries")
    parser.add_argument("--severity", choices=["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"], default="INFO", help="Filter by minimum severity level")
    parser.add_argument("--tenant", type=str, help="Filter findings by specific tenant namespace")
    parser.add_argument("--format", choices=["table", "json", "markdown"], default="table", help="Output formatting style")
    parser.add_argument("--generate-sample-file", type=str, help="Export a sample audit JSONL file to specified path")

    args = parser.parse_args()

    if args.generate_sample_file:
        samples = generate_sample_audit_events()
        with open(args.generate_sample_file, "w", encoding="utf-8") as f:
            for s in samples:
                f.write(json.dumps(s) + "\n")
        print(f"✓ Sample audit log successfully written to {args.generate_sample_file}")
        sys.exit(0)

    # Ingest audit events
    events: List[Dict[str, Any]] = []
    if args.log_file and os.path.exists(args.log_file):
        with open(args.log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    elif args.live:
        events = query_live_cluster_events(args.kubeconfig)
    else:
        events = generate_sample_audit_events()

    severity_order = {"INFO": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
    min_sev_rank = severity_order.get(args.severity, 0)

    analyzed_records = []
    severity_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}

    for ev in events:
        sev, rule = classify_event_severity(ev)
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

        if severity_order.get(sev, 0) < min_sev_rank:
            continue

        obj_ref = ev.get("objectRef", {})
        tenant_ns = obj_ref.get("namespace", "cluster-wide")
        if args.tenant and tenant_ns != args.tenant:
            continue

        timestamp = ev.get("requestReceivedTimestamp", "")[:19].replace("T", " ")
        user = ev.get("user", {}).get("username", "unknown")
        verb = ev.get("verb", "").upper()
        res_name = f"{obj_ref.get('resource', '')}/{obj_ref.get('name', '')}"
        if obj_ref.get("subresource"):
            res_name += f"/{obj_ref.get('subresource')}"
        status_code = ev.get("responseStatus", {}).get("code", 200)

        analyzed_records.append({
            "timestamp": timestamp,
            "severity": sev,
            "rule": rule,
            "user": user,
            "tenant": tenant_ns,
            "verb": verb,
            "resource": res_name,
            "status": status_code,
            "src_ip": ev.get("sourceIPs", ["-"])[0]
        })

    if args.format == "json":
        print(json.dumps({"summary": severity_counts, "records": analyzed_records}, indent=2))
        return

    # Print Table / Markdown format
    print("=" * 110)
    print("  GDC Air-Gapped Platform Security & Compliance Audit Log Inspector")
    print("=" * 110)
    print(f"  Total Events Analyzed: {len(events)} | Filter Minimum Severity: {args.severity}")
    print(f"  Critical: {severity_counts['CRITICAL']} | High: {severity_counts['HIGH']} | Medium: {severity_counts['MEDIUM']} | Low: {severity_counts['LOW']} | Info: {severity_counts['INFO']}")
    print("-" * 110)

    if not analyzed_records:
        print("  No audit events matching criteria.")
        return

    if args.format == "markdown":
        print("| Timestamp | Severity | Rule / Classification | Tenant | User | Verb | Target Resource | Status |")
        print("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for r in analyzed_records:
            print(f"| {r['timestamp']} | **{r['severity']}** | `{r['rule']}` | {r['tenant']} | {r['user']} | {r['verb']} | {r['resource']} | {r['status']} |")
    else:
        # ASCII Table
        header = f"{'Timestamp':<19} | {'Sev':<8} | {'Rule':<36} | {'Tenant':<16} | {'User':<22} | {'Status':<6}"
        print(header)
        print("-" * len(header))
        for r in analyzed_records:
            print(f"{r['timestamp']:<19} | {r['severity']:<8} | {r['rule']:<36} | {r['tenant']:<16} | {r['user'][:22]:<22} | {r['status']:<6}")

    print("=" * 110)
    if severity_counts["CRITICAL"] > 0 or severity_counts["HIGH"] > 0:
        print("⚠️  SECURITY ACTION REQUIRED: Unauthorized privilege escalation or policy tampering detected!")
    else:
        print("✓ All inspected events adhere to platform baseline security policies.")


if __name__ == "__main__":
    main()
