/**
 * Table - Renders flight results in table format
 */
const Table = {
    /**
     * Render flights to table body
     */
    render(flights, containerId = 'resultsBody') {
        const tbody = document.getElementById(containerId);
        if (!tbody) return;
        
        tbody.innerHTML = '';
        
        if (flights.length === 0) {
            return;
        }
        
        flights.forEach(flight => {
            const row = this.createRow(flight);
            tbody.appendChild(row);
        });
    },
    
    /**
     * Create a table row for a flight
     */
    createRow(flight) {
        const tr = document.createElement('tr');
        
        // Show cash price if available (Google Flights), otherwise show points
        const priceDisplay = flight.cash_price 
            ? `<span class="cash-price">$${flight.cash_price.toFixed(0)}</span>`
            : this.formatPoints(flight.points_required);
        
        tr.innerHTML = `
            <td class="program">${this.formatProgram(flight.source_program)}</td>
            <td>
                <strong>${flight.airline}</strong>
                <span class="flight-num">${flight.flight_number}</span>
            </td>
            <td>${flight.origin} → ${flight.destination}</td>
            <td>${this.formatDate(flight.departure_date)}</td>
            <td>${flight.departure_time || '-'}</td>
            <td>${flight.arrival_time || '-'}</td>
            <td>${this.formatDuration(flight.duration_minutes)}</td>
            <td class="cabin ${flight.cabin_class}">${this.formatCabin(flight.cabin_class)}</td>
            <td class="points">${priceDisplay}</td>
            <td>${this.formatTaxes(flight.taxes_fees)}</td>
            <td class="stops ${flight.stops === 0 ? 'direct' : ''}">${this.formatStops(flight.stops)}</td>
        `;
        
        return tr;
    },
    
    /**
     * Format program name for display
     */
    formatProgram(program) {
        const names = {
            'united_mileageplus': 'United MileagePlus',
            'aeroplan': 'Aeroplan',
            'google_flights': 'Google Flights',
            'jetblue_trueblue': 'JetBlue TrueBlue',
            'lufthansa_milesmore': 'Lufthansa M&M',
            'virgin_atlantic': 'Virgin Atlantic',
            'demo': 'Demo Mode',
        };
        return names[program] || program;
    },
    
    /**
     * Format date for display
     */
    formatDate(dateStr) {
        try {
            const date = new Date(dateStr);
            return date.toLocaleDateString('en-US', {
                weekday: 'short',
                month: 'short',
                day: 'numeric'
            });
        } catch {
            return dateStr;
        }
    },
    
    /**
     * Format duration in hours and minutes
     */
    formatDuration(minutes) {
        if (!minutes) return '-';
        const hours = Math.floor(minutes / 60);
        const mins = minutes % 60;
        return `${hours}h ${mins}m`;
    },
    
    /**
     * Format cabin class
     */
    formatCabin(cabin) {
        const names = {
            'economy': 'Economy',
            'premium_economy': 'Premium Eco',
            'business': 'Business',
            'first': 'First',
        };
        return names[cabin] || cabin;
    },
    
    /**
     * Format points with thousands separator
     */
    formatPoints(points) {
        return points.toLocaleString();
    },
    
    /**
     * Format taxes/fees as currency
     */
    formatTaxes(amount) {
        if (!amount) return '-';
        return '$' + amount.toFixed(2);
    },
    
    /**
     * Format stops display
     */
    formatStops(stops) {
        if (stops === 0) return 'Direct';
        if (stops === 1) return '1 stop';
        return `${stops} stops`;
    },
    
    /**
     * Clear the table
     */
    clear(containerId = 'resultsBody') {
        const tbody = document.getElementById(containerId);
        if (tbody) {
            tbody.innerHTML = '';
        }
    }
};
