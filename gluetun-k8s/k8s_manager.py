"""
Kubernetes API Manager for Gluetun VPN Containers

This module provides a high-level interface for managing Gluetun VPN containers
as Kubernetes pods using the Kubernetes Python client.
"""

import logging
import random
import string
import time
import uuid
from typing import Dict, Optional, List, Tuple

from kubernetes import client, config
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)


class GluetunK8sManager:
    """Manages Gluetun VPN containers as Kubernetes pods."""
    
    def __init__(self, namespace: str = "default", firewall_input_ports: Optional[str] = None):
        """
        Initialize the Kubernetes manager.
        
        Args:
            namespace: Kubernetes namespace to use for gluetun pods
            firewall_input_ports: Comma-separated list of ports to allow through Gluetun firewall
        """
        self.namespace = namespace
        self.firewall_input_ports = firewall_input_ports
        self.core_api = None
        self.apps_api = None
        self._load_k8s_config()
        
    def _load_k8s_config(self):
        """Load Kubernetes configuration (in-cluster or kubeconfig)."""
        try:
            # Try to load in-cluster config first (when running inside k8s)
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes configuration")
        except config.ConfigException:
            # Fall back to kubeconfig (when running locally)
            try:
                config.load_kube_config()
                logger.info("Loaded kubeconfig Kubernetes configuration")
            except config.ConfigException as e:
                logger.error(f"Failed to load Kubernetes config: {e}")
                raise
        
        self.core_api = client.CoreV1Api()
        self.apps_api = client.AppsV1Api()
    
    def _proxy_service_name(self, pod_id: str) -> str:
        return f"gluetun-proxy-{pod_id}"
    
    def _create_proxy_service(self, pod_id: str, port: int = 8888) -> Dict[str, str]:
        """Create a ClusterIP service pointing to the Gluetun pod."""
        service_name = self._proxy_service_name(pod_id)
        service_manifest = {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": service_name,
                "namespace": self.namespace,
                "labels": {
                    "app": "gluetun-vpn",
                    "managed-by": "gluetun-k8s-api",
                    "pod-id": pod_id,
                },
            },
            "spec": {
                "selector": {
                    "pod-id": pod_id,
                },
                "ports": [
                    {
                        "name": "proxy",
                        "port": port,
                        "targetPort": port,
                        "protocol": "TCP",
                    }
                ],
            },
        }
        
        self.core_api.create_namespaced_service(
            namespace=self.namespace,
            body=service_manifest,
        )
        
        # Retrieve service to get assigned ClusterIP
        service = self.core_api.read_namespaced_service(
            name=service_name,
            namespace=self.namespace,
        )
        cluster_ip = None
        if service and service.spec:
            cluster_ip = getattr(service.spec, "cluster_ip", None)
        
        return {
            "name": service_name,
            "cluster_ip": cluster_ip,
            "port": port,
            "dns": f"{service_name}.{self.namespace}.svc.cluster.local",
        }
    
    def _delete_proxy_service(self, pod_id: str):
        """Delete the proxy service associated with a Gluetun pod."""
        service_name = self._proxy_service_name(pod_id)
        try:
            self.core_api.delete_namespaced_service(
                name=service_name,
                namespace=self.namespace,
            )
            logger.info(f"Deleted proxy service: {service_name}")
        except ApiException as e:
            if e.status != 404:
                logger.error(f"Failed to delete proxy service {service_name}: {e}")
    
    def _get_proxy_service_info(self, pod_id: str) -> Dict[str, str]:
        """Retrieve proxy service information for a given pod."""
        service_name = self._proxy_service_name(pod_id)
        try:
            service = self.core_api.read_namespaced_service(
                name=service_name,
                namespace=self.namespace,
            )
            cluster_ip = None
            if service and service.spec:
                cluster_ip = getattr(service.spec, "cluster_ip", None)
                port = None
                if service.spec.ports:
                    port = service.spec.ports[0].port
                else:
                    port = 8888
            else:
                port = 8888
            return {
                "name": service_name,
                "cluster_ip": cluster_ip,
                "port": port,
                "dns": f"{service_name}.{self.namespace}.svc.cluster.local",
            }
        except ApiException as e:
            if e.status != 404:
                logger.error(f"Failed to get proxy service info for pod {pod_id}: {e}")
            return {
                "name": service_name,
                "cluster_ip": None,
                "port": 8888,
                "dns": f"{service_name}.{self.namespace}.svc.cluster.local",
            }
    
    def _generate_credentials(self) -> Tuple[str, str]:
        """Generate random username and password for proxy authentication."""
        username = "".join(random.choices(string.ascii_letters + string.digits, k=10))
        password = "".join(random.choices(string.ascii_letters + string.digits, k=10))
        return username, password
    
    def _build_gluetun_env(
        self,
        wireguard_private_key: str,
        wireguard_addresses: str,
        server_hostname: str,
        username: str,
        password: str,
    ) -> List[Dict[str, str]]:
        """Build environment variables for Gluetun pods."""
        env_vars = [
            {"name": "VPN_SERVICE_PROVIDER", "value": "mullvad"},
            {"name": "VPN_TYPE", "value": "wireguard"},
            {"name": "WIREGUARD_PRIVATE_KEY", "value": wireguard_private_key},
            {"name": "WIREGUARD_ADDRESSES", "value": wireguard_addresses},
            {"name": "SERVER_HOSTNAMES", "value": server_hostname},
            {"name": "HTTPPROXY", "value": "on"},
            {"name": "HTTPPROXY_USER", "value": username},
            {"name": "HTTPPROXY_PASSWORD", "value": password},
            {"name": "HTTPPROXY_LISTENING_ADDRESS", "value": ":8888"},
            {"name": "HTTPPROXY_LOG", "value": "off"},
            {"name": "HTTPPROXY_STEALTH", "value": "off"},
        ]
        if self.firewall_input_ports:
            env_vars.append({"name": "FIREWALL_INPUT_PORTS", "value": self.firewall_input_ports})
        env_vars.append({"name": "DNS_ADDRESS", "value": "8.8.8.8"})
        return env_vars
    
    def create_gluetun_pod(
        self,
        server_hostname: str,
        wireguard_private_key: str,
        wireguard_addresses: str,
        server_name: str = None,
    ) -> Dict[str, str]:
        """
        Create a Gluetun VPN pod in Kubernetes.
        
        Args:
            server_hostname: Mullvad server hostname
            wireguard_private_key: WireGuard private key
            wireguard_addresses: WireGuard IP addresses
            server_name: Human-readable server name (for tracking)
        
        Returns:
            Dictionary with pod information including id, proxy URL, and details
        """
        # Generate unique identifiers
        pod_id = str(uuid.uuid4())
        pod_name = f"gluetun-{pod_id}"
        username, password = self._generate_credentials()
        
        # Create pod specification
        pod_manifest = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": pod_name,
                "namespace": self.namespace,
                "labels": {
                    "app": "gluetun-vpn",
                    "managed-by": "gluetun-k8s-api",
                    "pod-id": pod_id,
                    "server-key": (server_name or server_hostname).lower(),
                },
                "annotations": {
                    "gluetun-server-key": server_name or server_hostname,
                },
            },
            "spec": {
                "containers": [
                    {
                        "name": "gluetun",
                        "image": "qmcgaw/gluetun:latest",
                        "securityContext": {
                            "capabilities": {
                                "add": ["NET_ADMIN"]
                            },
                            "privileged": False,
                        },
                        "env": self._build_gluetun_env(
                            wireguard_private_key=wireguard_private_key,
                            wireguard_addresses=wireguard_addresses,
                            server_hostname=server_hostname,
                            username=username,
                            password=password,
                        ),
                        "ports": [
                            {"name": "proxy", "containerPort": 8888, "protocol": "TCP"}
                        ],
                        "resources": {
                            "requests": {
                                "memory": "128Mi",
                                "cpu": "100m",
                            },
                            "limits": {
                                "memory": "256Mi",
                                "cpu": "500m",
                            },
                        },
                    }
                ],
                "restartPolicy": "Never",
            },
        }
        
        try:
            # Create the pod
            pod = self.core_api.create_namespaced_pod(
                namespace=self.namespace,
                body=pod_manifest
            )
            logger.info(f"Created Gluetun pod: {pod_name}")
            
            # Wait for pod to be ready
            pod_ready = self._wait_for_pod_ready(pod_name, timeout=90)
            if not pod_ready:
                logger.warning(f"Pod {pod_name} did not become ready within timeout")
                # Clean up if not ready
                self.delete_gluetun_pod(pod_id)
                raise Exception("Pod did not become ready within timeout period")
            
            # Get pod IP address
            pod = self.core_api.read_namespaced_pod(name=pod_name, namespace=self.namespace)
            pod_ip = pod.status.pod_ip
            
            if not pod_ip:
                logger.error(f"Pod {pod_name} has no IP address")
                self.delete_gluetun_pod(pod_id)
                raise Exception("Pod has no IP address")
            
            # Construct proxy URL using pod IP
            proxy_url = f"http://{username}:{password}@{pod_ip}:8888"
            
            result = {
                "id": pod_id,
                "pod_name": pod_name,
                "pod_ip": pod_ip,
                "proxy": proxy_url,
                "server": server_name or server_hostname,
                "username": username,
                "password": password,
                "port": 8888,
                "status": "running",
            }
            
            try:
                service_info = self._create_proxy_service(pod_id)
                service_url = None
                if service_info.get("dns") and service_info.get("port"):
                    service_url = f"http://{username}:{password}@{service_info['dns']}:{service_info['port']}"
                result.update({
                    "service_name": service_info.get("name"),
                    "service_cluster_ip": service_info.get("cluster_ip"),
                    "service_dns": service_info.get("dns"),
                    "service_port": service_info.get("port"),
                    "service_url": service_url,
                })
                logger.info(f"Created proxy service {service_info.get('name')} for pod {pod_name}")
            except ApiException as e:
                logger.error(f"Failed to create proxy service for pod {pod_name}: {e}")
                # Clean up pod if service creation fails
                self.delete_gluetun_pod(pod_id)
                raise Exception("Failed to create proxy service for Gluetun pod") from e
            
            return result
            
        except ApiException as e:
            logger.error(f"Failed to create Gluetun pod: {e}")
            raise
    
    def _wait_for_pod_ready(self, pod_name: str, timeout: int = 90) -> bool:
        """
        Wait for a pod to be in Running state and ready.
        
        Args:
            pod_name: Name of the pod
            timeout: Maximum time to wait in seconds
        
        Returns:
            True if pod is ready, False if timeout
        """
        logger.info(f"Waiting for pod {pod_name} to be ready (timeout: {timeout}s)")
        start_time = time.time()
        check_interval = 2
        
        while time.time() - start_time < timeout:
            try:
                pod = self.core_api.read_namespaced_pod(
                    name=pod_name,
                    namespace=self.namespace
                )
                
                # Check if pod is running
                if pod.status.phase == "Running":
                    # Check if all containers are ready
                    if pod.status.conditions:
                        for condition in pod.status.conditions:
                            if condition.type == "Ready" and condition.status == "True":
                                elapsed = time.time() - start_time
                                logger.info(f"Pod {pod_name} is ready after {elapsed:.1f}s")
                                return True
                
                # Check if pod failed
                if pod.status.phase in ["Failed", "Unknown"]:
                    logger.error(f"Pod {pod_name} is in {pod.status.phase} state")
                    return False
                
            except ApiException as e:
                logger.warning(f"Error checking pod status: {e}")
                return False
            
            time.sleep(check_interval)
        
        logger.warning(f"Pod {pod_name} did not become ready within {timeout}s")
        return False
    
    def delete_gluetun_pod(self, pod_id: str) -> bool:
        """
        Delete a Gluetun pod by its ID.
        
        Args:
            pod_id: Unique pod ID (UUID)
        
        Returns:
            True if deleted successfully, False otherwise
        """
        pod_name = f"gluetun-{pod_id}"
        
        try:
            # Delete associated service first
            self._delete_proxy_service(pod_id)
            
            self.core_api.delete_namespaced_pod(
                name=pod_name,
                namespace=self.namespace,
                grace_period_seconds=5,
            )
            logger.info(f"Deleted Gluetun pod: {pod_name}")
            return True
        except ApiException as e:
            if e.status == 404:
                logger.warning(f"Pod {pod_name} not found (may have been already deleted)")
                return True
            logger.error(f"Failed to delete pod {pod_name}: {e}")
            return False
    
    def get_gluetun_pod(self, pod_id: str) -> Optional[Dict[str, str]]:
        """
        Get information about a Gluetun pod.
        
        Args:
            pod_id: Unique pod ID (UUID)
        
        Returns:
            Dictionary with pod information or None if not found
        """
        pod_name = f"gluetun-{pod_id}"
        
        try:
            pod = self.core_api.read_namespaced_pod(
                name=pod_name,
                namespace=self.namespace
            )
            
            # Extract credentials from environment variables
            username = None
            password = None
            server = None
            
            if pod.spec.containers:
                for env_var in pod.spec.containers[0].env:
                    if env_var.name == "HTTPPROXY_USER":
                        username = env_var.value
                    elif env_var.name == "HTTPPROXY_PASSWORD":
                        password = env_var.value
                    elif env_var.name == "SERVER_HOSTNAMES":
                        server = env_var.value
            
            if pod.metadata.annotations:
                server_key = pod.metadata.annotations.get("gluetun-server-key")
                if server_key:
                    server = server_key
            if not server and pod.metadata.labels:
                server_label = pod.metadata.labels.get("server-key")
                if server_label:
                    server = server_label
            
            return {
                "id": pod_id,
                "pod_name": pod_name,
                "pod_ip": pod.status.pod_ip,
                "proxy": f"http://{username}:{password}@{pod.status.pod_ip}:8888" if username and password else None,
                "server": server,
                "username": username,
                "password": password,
                "port": 8888,
                "service_name": service_info.get("name"),
                "service_cluster_ip": service_info.get("cluster_ip"),
                "service_dns": service_info.get("dns"),
                "service_port": service_info.get("port"),
                "service_url": f"http://{username}:{password}@{service_info['dns']}:{service_info['port']}" if service_info.get("dns") and service_info.get("port") and username and password else None,
                "status": pod.status.phase.lower(),
            }
            
        except ApiException as e:
            if e.status == 404:
                return None
            logger.error(f"Failed to get pod {pod_name}: {e}")
            return None
    
    def list_gluetun_pods(self) -> List[Dict[str, str]]:
        """
        List all Gluetun pods managed by this API.
        
        Returns:
            List of dictionaries with pod information
        """
        try:
            pods = self.core_api.list_namespaced_pod(
                namespace=self.namespace,
                label_selector="managed-by=gluetun-k8s-api"
            )
            
            result = []
            for pod in pods.items:
                # Extract pod ID from labels
                pod_id = pod.metadata.labels.get("pod-id", "")
                if not pod_id:
                    continue
                
                service_info = self._get_proxy_service_info(pod_id)
                
                # Extract credentials from environment variables
                username = None
                password = None
                server = None
                
                if pod.spec.containers:
                    for env_var in pod.spec.containers[0].env:
                        if env_var.name == "HTTPPROXY_USER":
                            username = env_var.value
                        elif env_var.name == "HTTPPROXY_PASSWORD":
                            password = env_var.value
                        elif env_var.name == "SERVER_HOSTNAMES":
                            server = env_var.value
                
                if pod.metadata.annotations:
                    server_key = pod.metadata.annotations.get("gluetun-server-key")
                    if server_key:
                        server = server_key
                if not server and pod.metadata.labels:
                    server_label = pod.metadata.labels.get("server-key")
                    if server_label:
                        server = server_label
                
                result.append({
                    "id": pod_id,
                    "pod_name": pod.metadata.name,
                    "pod_ip": pod.status.pod_ip,
                    "proxy": f"http://{username}:{password}@{pod.status.pod_ip}:8888" if username and password and pod.status.pod_ip else None,
                    "server": server,
                    "username": username,
                    "password": password,
                    "port": 8888,
                    "service_name": service_info.get("name"),
                    "service_cluster_ip": service_info.get("cluster_ip"),
                    "service_dns": service_info.get("dns"),
                    "service_port": service_info.get("port"),
                    "service_url": f"http://{username}:{password}@{service_info['dns']}:{service_info['port']}" if service_info.get("dns") and service_info.get("port") and username and password else None,
                    "status": pod.status.phase.lower() if pod.status else "unknown",
                })
            
            return result
            
        except ApiException as e:
            logger.error(f"Failed to list Gluetun pods: {e}")
            return []
    
    def cleanup_failed_pods(self) -> int:
        """
        Clean up any failed or completed Gluetun pods.
        
        Returns:
            Number of pods cleaned up
        """
        try:
            pods = self.core_api.list_namespaced_pod(
                namespace=self.namespace,
                label_selector="managed-by=gluetun-k8s-api"
            )
            
            cleaned = 0
            for pod in pods.items:
                if pod.status.phase in ["Failed", "Succeeded", "Unknown"]:
                    pod_id = pod.metadata.labels.get("pod-id", "")
                    if pod_id:
                        if self.delete_gluetun_pod(pod_id):
                            cleaned += 1
            
            if cleaned > 0:
                logger.info(f"Cleaned up {cleaned} failed/completed pods")
            
            return cleaned
            
        except ApiException as e:
            logger.error(f"Failed to cleanup failed pods: {e}")
            return 0

