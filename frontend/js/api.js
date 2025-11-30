/**
 * API Client - Handles communication with backend
 */
const API = {
    BASE_URL: 'http://localhost:8000',
    
    /**
     * Search for award flights
     */
    async searchFlights(params) {
        const response = await fetch(`${this.BASE_URL}/api/search`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(params),
        });
        
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Search failed' }));
            throw new Error(error.detail || 'Search failed');
        }
        
        return response.json();
    },
    
    /**
     * Get cached availability with filters
     */
    async getAvailability(params) {
        const queryParams = new URLSearchParams();
        
        Object.entries(params).forEach(([key, value]) => {
            if (value !== undefined && value !== null && value !== '') {
                queryParams.append(key, value);
            }
        });
        
        const response = await fetch(`${this.BASE_URL}/api/availability?${queryParams}`);
        
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Query failed' }));
            throw new Error(error.detail || 'Query failed');
        }
        
        return response.json();
    },
    
    /**
     * Get list of loyalty programs
     */
    async getPrograms() {
        const response = await fetch(`${this.BASE_URL}/api/programs`);
        
        if (!response.ok) {
            throw new Error('Failed to fetch programs');
        }
        
        return response.json();
    },
    
    /**
     * Trigger a scrape job
     */
    async triggerScrape(params) {
        const response = await fetch(`${this.BASE_URL}/api/scrape`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(params),
        });
        
        if (!response.ok) {
            throw new Error('Scrape trigger failed');
        }
        
        return response.json();
    },
    
    /**
     * Get store statistics
     */
    async getStats() {
        const response = await fetch(`${this.BASE_URL}/stats`);
        
        if (!response.ok) {
            throw new Error('Failed to fetch stats');
        }
        
        return response.json();
    },
    
    /**
     * Health check
     */
    async healthCheck() {
        try {
            const response = await fetch(`${this.BASE_URL}/health`);
            return response.ok;
        } catch {
            return false;
        }
    }
};
