import Keycloak from 'keycloak-js';

// Default configuration points to the Keycloak instance.
// When accessing via port-forward or ingress, window.location.hostname is used.
// KEYCLOAK_URL can be overridden at runtime via window._env_ or localStorage if needed.
const keycloakUrl =
  (window as any)?._env_?.KEYCLOAK_URL ||
  localStorage.getItem('KEYCLOAK_URL') ||
  `${window.location.protocol}//${window.location.hostname}:8080`;

export const keycloak = new Keycloak({
  url: keycloakUrl,
  realm: (window as any)?._env_?.KEYCLOAK_REALM || 'sandbox',
  clientId: (window as any)?._env_?.KEYCLOAK_CLIENT_ID || 'sandbox-client',
});

export const getKeycloakUrl = () => keycloakUrl;
