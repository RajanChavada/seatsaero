/**
 * App - Main application logic
 */
document.addEventListener('DOMContentLoaded', () => {
    const App = {
        // Store current results for filtering
        currentResults: [],
        
        /**
         * Initialize the application
         */
        init() {
            this.setDefaultDate();
            this.bindEvents();
            this.checkBackendHealth();
        },
        
        /**
         * Set default departure date to tomorrow
         */
        setDefaultDate() {
            const dateInput = document.getElementById('departureDate');
            if (dateInput) {
                const tomorrow = new Date();
                tomorrow.setDate(tomorrow.getDate() + 1);
                dateInput.valueAsDate = tomorrow;
            }
        },
        
        /**
         * Bind event listeners
         */
        bindEvents() {
            // Search form submission
            const searchForm = document.getElementById('searchForm');
            if (searchForm) {
                searchForm.addEventListener('submit', (e) => {
                    e.preventDefault();
                    this.handleSearch();
                });
            }
            
            // Apply filters button
            const applyFiltersBtn = document.getElementById('applyFilters');
            if (applyFiltersBtn) {
                applyFiltersBtn.addEventListener('click', () => {
                    this.applyFilters();
                });
            }
            
            // Sort change
            const sortSelect = document.getElementById('sortBy');
            if (sortSelect) {
                sortSelect.addEventListener('change', () => {
                    this.applyFilters();
                });
            }
            
            // Real-time filter on checkbox
            const directOnly = document.getElementById('filterDirectOnly');
            if (directOnly) {
                directOnly.addEventListener('change', () => {
                    this.applyFilters();
                });
            }
        },
        
        /**
         * Check if backend is healthy
         */
        async checkBackendHealth() {
            const isHealthy = await API.healthCheck();
            if (!isHealthy) {
                this.showError('Backend API is not available. Make sure the server is running on port 8000.');
            }
        },
        
        /**
         * Handle search form submission
         */
        async handleSearch() {
            const origin = document.getElementById('origin').value.toUpperCase();
            const destination = document.getElementById('destination').value.toUpperCase();
            const departureDate = document.getElementById('departureDate').value;
            const cabin = document.getElementById('cabin').value;
            
            if (!origin || !destination || !departureDate) {
                this.showError('Please fill in all required fields');
                return;
            }
            
            // Show loading
            this.showLoading(true);
            this.hideError();
            this.hideResults();
            
            try {
                const response = await API.searchFlights({
                    origin,
                    destination,
                    departure_date: departureDate,
                    cabin_class: cabin || null,
                    passengers: 1,
                });
                
                this.currentResults = response.flights || [];
                this.displayResults(this.currentResults);
                
            } catch (error) {
                console.error('Search error:', error);
                this.showError(error.message || 'Search failed. Please try again.');
            } finally {
                this.showLoading(false);
            }
        },
        
        /**
         * Apply filters to current results
         */
        applyFilters() {
            if (this.currentResults.length === 0) return;
            
            const filters = Filters.getFromUI();
            let filtered = Filters.apply(this.currentResults, filters);
            filtered = Filters.sort(filtered, filters.sortBy);
            
            this.displayResults(filtered, false);
        },
        
        /**
         * Display flight results
         */
        displayResults(flights, updateStore = true) {
            if (updateStore) {
                this.currentResults = flights;
            }
            
            const resultsSection = document.getElementById('resultsSection');
            const noResults = document.getElementById('noResults');
            const resultsCount = document.getElementById('resultsCount');
            
            if (flights.length === 0) {
                resultsSection?.classList.add('hidden');
                noResults?.classList.remove('hidden');
                return;
            }
            
            noResults?.classList.add('hidden');
            resultsSection?.classList.remove('hidden');
            
            // Update count
            if (resultsCount) {
                resultsCount.textContent = `${flights.length} flight${flights.length !== 1 ? 's' : ''} found`;
            }
            
            // Render table
            Table.render(flights);
        },
        
        /**
         * Show/hide loading indicator
         */
        showLoading(show) {
            const loading = document.getElementById('loading');
            const searchBtn = document.getElementById('searchBtn');
            
            if (loading) {
                loading.classList.toggle('hidden', !show);
            }
            
            if (searchBtn) {
                searchBtn.disabled = show;
                searchBtn.textContent = show ? 'Searching...' : '🔍 Search Flights';
            }
        },
        
        /**
         * Show error message
         */
        showError(message) {
            const errorDiv = document.getElementById('errorMessage');
            const errorText = document.getElementById('errorText');
            
            if (errorDiv && errorText) {
                errorText.textContent = message;
                errorDiv.classList.remove('hidden');
            }
        },
        
        /**
         * Hide error message
         */
        hideError() {
            const errorDiv = document.getElementById('errorMessage');
            if (errorDiv) {
                errorDiv.classList.add('hidden');
            }
        },
        
        /**
         * Hide results section
         */
        hideResults() {
            const resultsSection = document.getElementById('resultsSection');
            const noResults = document.getElementById('noResults');
            
            resultsSection?.classList.add('hidden');
            noResults?.classList.add('hidden');
        }
    };
    
    // Initialize app
    App.init();
});
