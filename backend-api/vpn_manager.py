"""VPN Manager for Gluetun containers via Docker API."""
import os
import logging
from typing import Optional, Dict, Any
import docker
from docker.errors import DockerException, APIError, NotFound

logger = logging.getLogger(__name__)

class GluetunManager:
    """Manages Gluetun VPN containers via Docker API."""
    
    CONTAINER_NAME = "geosnappro-gluetun"
    IMAGE = "qmcgaw/gluetun:latest"
    PROXY_PORT = 8888
    
    def __init__(self):
        """Initialize Docker client and validate Mullvad credentials."""
        docker_host = os.getenv("DOCKER_HOST")
        if docker_host:
            # Handle both unix:// and http:// URLs
            if docker_host.startswith("unix://"):
                base_url = docker_host
            elif docker_host.startswith("http://") or docker_host.startswith("https://"):
                base_url = docker_host
            else:
                # Assume HTTP if no protocol specified
                base_url = f"http://{docker_host}"
        else:
            # Default to unix socket
            base_url = "unix://var/run/docker.sock"
        
        try:
            if base_url.startswith("unix://"):
                # For unix socket, use default client
                self.client = docker.from_env()
            else:
                # For HTTP, create client with base_url
                self.client = docker.DockerClient(base_url=base_url)
        except Exception as e:
            logger.error(f"Failed to initialize Docker client: {e}")
            raise DockerException(f"Could not connect to Docker: {e}")
        
        # Validate Mullvad account number
        self.mullvad_account = os.getenv("MULLVAD_ACCOUNT_NUMBER")
        if not self.mullvad_account:
            logger.warning("MULLVAD_ACCOUNT_NUMBER not set - VPN features will not work")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current gluetun container status."""
        try:
            container = self.client.containers.get(self.CONTAINER_NAME)
            
            # Check if container is running
            container.reload()
            is_running = container.status == "running"
            
            # Get proxy URL
            proxy_url = None
            if is_running:
                # With bridge network, backend container can access gluetun via container name
                # This works when both containers are on the same Docker network (default bridge)
                proxy_url = f"http://{self.CONTAINER_NAME}:{self.PROXY_PORT}"
            
            return {
                "active": is_running,
                "container_name": self.CONTAINER_NAME,
                "proxy_url": proxy_url,
                "status": container.status,
                "image": container.image.tags[0] if container.image.tags else self.IMAGE,
            }
        except NotFound:
            return {
                "active": False,
                "container_name": self.CONTAINER_NAME,
                "proxy_url": None,
                "status": "not_found",
            }
        except Exception as e:
            logger.error(f"Error getting container status: {e}")
            return {
                "active": False,
                "container_name": self.CONTAINER_NAME,
                "proxy_url": None,
                "status": "error",
                "error": str(e),
            }
    
    def start(self, location: Optional[str] = None) -> Dict[str, Any]:
        """Start gluetun container with specified location."""
        if not self.mullvad_account:
            raise ValueError("MULLVAD_ACCOUNT_NUMBER environment variable not set")
        
        # Stop existing container if it exists
        try:
            self.stop()
        except Exception as e:
            logger.warning(f"Error stopping existing container: {e}")
        
        # Build environment variables for gluetun
        # Use VPN_SERVICE_PROVIDER instead of VPNSP (new format)
        # Mullvad uses WireGuard by default
        # Explicitly clear any conflicting defaults by setting them to empty or correct values
        env_vars = {
            "VPN_SERVICE_PROVIDER": "mullvad",
            "VPNSP": "",  # Clear old variable
            "MULLVAD_ACCOUNT_NUMBER": self.mullvad_account,
            "VPN_TYPE": "wireguard",  # Explicitly use WireGuard for Mullvad
            "HTTP_CONTROL_SERVER": "true",
            "HTTP_CONTROL_SERVER_PORT": str(self.PROXY_PORT),
            # Explicitly clear server selection variables to avoid conflicts
            "SERVER_COUNTRIES": "",
            "SERVER_CITIES": "",
        }
        
        # Add location configuration
        if location:
            # Mullvad accepts country codes (e.g., "us") or full city names (e.g., "New York NY")
            # Common format conversions for short codes:
            location_map = {
                "us-nyc": "New York NY",
                "us-lax": "Los Angeles CA",
                "us-chi": "Chicago IL",
                "us-sf": "San Jose CA",
                "us-mia": "Miami FL",
                "uk-lon": "London",
                "de-fra": "Frankfurt",
                "fr-par": "Paris",
                "nl-ams": "Amsterdam",
                "jp-tok": "Tokyo",
            }
            
            # Check if location needs mapping from short code
            mapped_location = location_map.get(location.lower(), location)
            
            # Determine if it's a city name or country code
            # City names typically have multiple words
            # Country codes are typically 2-3 letter codes (like "us", "uk", "jp")
            words = mapped_location.split()
            has_multiple_words = len(words) > 1
            is_short_code = len(mapped_location) <= 3 and mapped_location.isupper()
            was_mapped = mapped_location != location
            
            logger.info(f"Location processing: input='{location}', mapped='{mapped_location}', words={words}, multiple={has_multiple_words}, short_code={is_short_code}, mapped={was_mapped}")
            logger.info(f"Checking conditions: has_dash={'-' in location}, in_map={location.lower() in location_map}, has_multiple={has_multiple_words}, was_mapped={was_mapped}, is_short={is_short_code}")
            
            # Remove empty strings first, then set the correct value
            if "SERVER_COUNTRIES" in env_vars and env_vars["SERVER_COUNTRIES"] == "":
                del env_vars["SERVER_COUNTRIES"]
            if "SERVER_CITIES" in env_vars and env_vars["SERVER_CITIES"] == "":
                del env_vars["SERVER_CITIES"]
            
            if "-" in location and location.lower() not in location_map:
                # Dash format but not in our map - extract country code
                country_code = location.split("-")[0].upper()
                if "SERVER_CITIES" in env_vars:
                    del env_vars["SERVER_CITIES"]
                env_vars["SERVER_COUNTRIES"] = country_code
                logger.info(f"Set SERVER_COUNTRIES to {country_code} (extracted from dash format)")
            elif has_multiple_words or was_mapped:
                # Multiple words = city name, or was mapped from short code = city name
                if "SERVER_COUNTRIES" in env_vars:
                    del env_vars["SERVER_COUNTRIES"]
                env_vars["SERVER_CITIES"] = mapped_location
                logger.info(f"Set SERVER_CITIES to '{mapped_location}' (city name)")
            elif is_short_code:
                # Short uppercase code = country code
                # Map common country codes to full names that gluetun expects
                country_map = {
                    "US": "USA",
                    "UK": "UK",
                    "JP": "Japan",
                }
                country_name = country_map.get(mapped_location.upper(), mapped_location.upper())
                if "SERVER_CITIES" in env_vars:
                    del env_vars["SERVER_CITIES"]
                env_vars["SERVER_COUNTRIES"] = country_name
                logger.info(f"Set SERVER_COUNTRIES to {country_name} (country code: {mapped_location})")
            else:
                # Default: assume it's a city name if it's not a clear country code
                if "SERVER_COUNTRIES" in env_vars:
                    del env_vars["SERVER_COUNTRIES"]
                env_vars["SERVER_CITIES"] = mapped_location
                logger.info(f"Set SERVER_CITIES to '{mapped_location}' (default assumption)")
        
        # Port mapping
        ports = {
            f"{self.PROXY_PORT}/tcp": self.PROXY_PORT,
        }
        
        try:
            # Pull image if needed
            try:
                self.client.images.get(self.IMAGE)
            except NotFound:
                logger.info(f"Pulling image {self.IMAGE}...")
                self.client.images.pull(self.IMAGE)
            
            # Log the final environment variables for debugging
            logger.info(f"Starting gluetun container with env vars: {list(env_vars.keys())}")
            logger.info(f"VPN_SERVICE_PROVIDER={env_vars.get('VPN_SERVICE_PROVIDER')}, VPN_TYPE={env_vars.get('VPN_TYPE')}, SERVER_CITIES={env_vars.get('SERVER_CITIES', 'NOT SET')}, SERVER_COUNTRIES={env_vars.get('SERVER_COUNTRIES', 'NOT SET')}")
            
            # Create and start container
            # Gluetun requires NET_ADMIN capability and /dev/net/tun device
            # Ensure environment variables are passed correctly (remove empty strings)
            clean_env = {k: v for k, v in env_vars.items() if v != ""}
            logger.info(f"Clean env vars: VPN_SERVICE_PROVIDER={clean_env.get('VPN_SERVICE_PROVIDER')}, VPN_TYPE={clean_env.get('VPN_TYPE')}")
            
            container = self.client.containers.run(
                image=self.IMAGE,
                name=self.CONTAINER_NAME,
                environment=clean_env,
                ports=ports,
                detach=True,
                restart_policy={"Name": "unless-stopped"},
                network_mode="bridge",  # Use bridge network to be accessible from other containers
                cap_add=["NET_ADMIN"],
                devices=["/dev/net/tun:/dev/net/tun"],
            )
            
            # Wait a moment for container to initialize
            import time
            time.sleep(2)
            
            # Reload to get current status
            container.reload()
            
            return {
                "success": True,
                "container_id": container.id[:12],
                "status": container.status,
                "proxy_url": f"http://{self.CONTAINER_NAME}:{self.PROXY_PORT}",
                "location": location,
            }
        except APIError as e:
            logger.error(f"Docker API error starting container: {e}")
            raise DockerException(f"Failed to start container: {e}")
        except Exception as e:
            logger.error(f"Error starting container: {e}")
            raise DockerException(f"Failed to start container: {e}")
    
    def stop(self) -> Dict[str, Any]:
        """Stop and remove gluetun container."""
        try:
            container = self.client.containers.get(self.CONTAINER_NAME)
            container.stop()
            container.remove()
            return {
                "success": True,
                "message": f"Container {self.CONTAINER_NAME} stopped and removed",
            }
        except NotFound:
            return {
                "success": True,
                "message": f"Container {self.CONTAINER_NAME} not found",
            }
        except Exception as e:
            logger.error(f"Error stopping container: {e}")
            raise DockerException(f"Failed to stop container: {e}")

