import React, { useState } from 'react';
import {
    Box,
    TextField,
    Button,
    Select,
    MenuItem,
    FormControl,
    InputLabel,
    Typography,
    Paper,
    CircularProgress,
    Alert
} from '@mui/material';
import axios from 'axios';

interface AccessVerification {
    verified: boolean;
    mode: string;
    username?: string;
    email?: string;
    nationality?: string;
    clearance?: string;
    service_branch?: string;
    rank?: string;
    rank_grade?: string;
    coi?: string;
    mission_id?: string;
    error?: string;
    message?: string;
}

interface TranslationResponse {
    translated_text: string;
    detected_source_language?: string;
    access_verification?: AccessVerification;
}

interface TranslationFormProps {
    authToken?: string;
}

const TranslationForm: React.FC<TranslationFormProps> = ({ authToken }) => {
    const [text, setText] = useState('');
    const [targetLanguage, setTargetLanguage] = useState('es');
    const [translatedText, setTranslatedText] = useState('');
    const [accessVerification, setAccessVerification] = useState<AccessVerification | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const handleTranslate = async () => {
        if (!text) return;

        setLoading(true);
        setError('');
        setTranslatedText('');
        setAccessVerification(null);

        try {
            const headers: Record<string, string> = {};
            if (authToken) {
                headers['Authorization'] = `Bearer ${authToken}`;
            }

            const response = await axios.post('/translate', {
                text: text,
                target_language: targetLanguage
            }, { headers });

            const data = response.data as TranslationResponse;
            setTranslatedText(data.translated_text);
            if (data.access_verification) {
                setAccessVerification(data.access_verification);
            }
        } catch (err: any) {
            console.error("Translation error:", err);
            setError(err.response?.data?.error || 'Failed to translate');
        } finally {
            setLoading(false);
        }
    };

    return (
        <Paper elevation={3} sx={{ p: 4, width: 500, mx: 'auto', mt: 4 }}>
            <Typography variant="h4" gutterBottom align="center" color="primary">
                Translator
            </Typography>

            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                <TextField
                    label="Text to Translate"
                    multiline
                    rows={4}
                    variant="outlined"
                    fullWidth
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                />

                <FormControl fullWidth>
                    <InputLabel>Target Language</InputLabel>
                    <Select
                        value={targetLanguage}
                        label="Target Language"
                        onChange={(e) => setTargetLanguage(e.target.value)}
                    >
                        <MenuItem value="es">Spanish</MenuItem>
                        <MenuItem value="fr">French</MenuItem>
                        <MenuItem value="de">German</MenuItem>
                        <MenuItem value="it">Italian</MenuItem>
                        <MenuItem value="ja">Japanese</MenuItem>
                        <MenuItem value="zh">Chinese</MenuItem>
                        <MenuItem value="ru">Russian</MenuItem>
                    </Select>
                </FormControl>

                <Button
                    variant="contained"
                    size="large"
                    onClick={handleTranslate}
                    disabled={loading || !text}
                >
                    {loading ? <CircularProgress size={24} /> : 'Translate'}
                </Button>

                {error && <Alert severity="error">{error}</Alert>}

                {accessVerification && (
                    <Alert
                        severity={accessVerification.verified ? "success" : "info"}
                        sx={{ fontSize: '0.85rem' }}
                    >
                        {accessVerification.verified ? (
                            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                                <Box sx={{ fontWeight: 'bold' }}>
                                    Server Verified with Keycloak: {accessVerification.username} ({accessVerification.email || 'no email'})
                                </Box>
                                <Box sx={{ fontSize: '0.8rem', color: 'text.secondary' }}>
                                    {[
                                        accessVerification.nationality && `Nat: ${accessVerification.nationality}`,
                                        accessVerification.clearance && `Clearance: ${accessVerification.clearance}`,
                                        accessVerification.service_branch && `Branch: ${accessVerification.service_branch}`,
                                        accessVerification.rank && `Rank: ${accessVerification.rank}${accessVerification.rank_grade ? ` (${accessVerification.rank_grade})` : ''}`,
                                        accessVerification.coi && `COI: ${accessVerification.coi}`,
                                        accessVerification.mission_id && `Mission: ${accessVerification.mission_id}`
                                    ].filter(Boolean).join(' | ')}
                                </Box>
                            </Box>
                        ) : (
                            `Server Access Status: ${accessVerification.error || accessVerification.message || accessVerification.mode}`
                        )}
                    </Alert>
                )}

                {translatedText && (
                    <Box sx={{ mt: 2, p: 2, bgcolor: 'background.default', borderRadius: 1 }}>
                        <Typography variant="subtitle2" color="text.secondary">
                            Translation:
                        </Typography>
                        <Typography variant="h6">
                            {translatedText}
                        </Typography>
                    </Box>
                )}
            </Box>
        </Paper>
    );
};

export default TranslationForm;
