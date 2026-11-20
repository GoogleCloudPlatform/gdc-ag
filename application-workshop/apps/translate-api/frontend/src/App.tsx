import { useState, useEffect } from 'react';
import {
  createTheme,
  ThemeProvider,
  CssBaseline,
  Container,
  AppBar,
  Toolbar,
  Typography,
  Button,
  Box,
  Chip,
  Tooltip
} from '@mui/material';
import LockIcon from '@mui/icons-material/Lock';
import LockOpenIcon from '@mui/icons-material/LockOpen';
import PersonIcon from '@mui/icons-material/Person';
import TranslationForm from './TranslationForm';
import { keycloak, getKeycloakUrl } from './keycloak';

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#1976d2',
    },
    background: {
      default: '#f5f5f5',
    },
  },
});

function App() {
  const [keycloakAvailable, setKeycloakAvailable] = useState<boolean>(false);
  const [authenticated, setAuthenticated] = useState<boolean>(false);
  const [username, setUsername] = useState<string>('');
  const [token, setToken] = useState<string>('');

  useEffect(() => {
    // Attempt graceful Keycloak initialization without blocking the app if Keycloak isn't reachable
    keycloak
      .init({
        onLoad: 'check-sso',
        silentCheckSsoRedirectUri: `${window.location.origin}/silent-check-sso.html`,
        checkLoginIframe: false,
        pkceMethod: 'S256',
      })
      .then((isAuth) => {
        setKeycloakAvailable(true);
        setAuthenticated(isAuth);
        if (isAuth) {
          setUsername(
            keycloak.tokenParsed?.preferred_username ||
              keycloak.tokenParsed?.name ||
              'Authenticated User'
          );
          setToken(keycloak.token || '');
        }
      })
      .catch((err) => {
        // Keycloak unreachable or not configured; fallback gracefully
        console.warn('Keycloak not reachable or unconfigured, running in guest/standalone mode:', err);
        setKeycloakAvailable(false);
      });
  }, []);

  const handleLogin = () => {
    keycloak.login({
      redirectUri: window.location.href,
    });
  };

  const handleLogout = () => {
    keycloak.logout({
      redirectUri: window.location.origin,
    });
  };

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <AppBar position="static" elevation={1} color="default" sx={{ bgcolor: '#ffffff' }}>
        <Toolbar>
          <Typography variant="h6" component="div" sx={{ flexGrow: 1, fontWeight: 'bold' }}>
            Translation App
          </Typography>

          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            {authenticated ? (
              <>
                <Chip
                  icon={<PersonIcon />}
                  label={username}
                  color="primary"
                  variant="outlined"
                />
                <Button
                  variant="outlined"
                  size="small"
                  color="secondary"
                  onClick={handleLogout}
                  startIcon={<LockOpenIcon />}
                >
                  Logout
                </Button>
              </>
            ) : keycloakAvailable ? (
              <Button
                variant="contained"
                size="small"
                color="primary"
                onClick={handleLogin}
                startIcon={<LockIcon />}
              >
                Sign in with Keycloak
              </Button>
            ) : (
              <Tooltip title={`Keycloak unreachable at ${getKeycloakUrl()} (running in standalone mode)`}>
                <Chip label="Standalone Mode" size="small" variant="outlined" />
              </Tooltip>
            )}
          </Box>
        </Toolbar>
      </AppBar>

      <Container maxWidth="md" sx={{ mt: 4 }}>
        <TranslationForm authToken={token} />
      </Container>
    </ThemeProvider>
  );
}

export default App;
