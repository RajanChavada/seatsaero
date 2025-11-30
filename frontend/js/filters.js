/**
 * Filters - Client-side filtering utilities
 */
const Filters = {
    /**
     * Apply filters to flight results
     */
    apply(flights, filters) {
        return flights.filter(flight => {
            // Program filter
            if (filters.program && flight.source_program !== filters.program) {
                return false;
            }
            
            // Max points filter
            if (filters.maxPoints && flight.points_required > filters.maxPoints) {
                return false;
            }
            
            // Direct only filter
            if (filters.directOnly && flight.stops > 0) {
                return false;
            }
            
            // Cabin class filter
            if (filters.cabin && flight.cabin_class !== filters.cabin) {
                return false;
            }
            
            // Airlines filter
            if (filters.airlines && filters.airlines.length > 0) {
                if (!filters.airlines.includes(flight.airline)) {
                    return false;
                }
            }
            
            return true;
        });
    },
    
    /**
     * Sort flights by specified field
     */
    sort(flights, sortBy) {
        const sorted = [...flights];
        
        switch (sortBy) {
            case 'points':
                sorted.sort((a, b) => a.points_required - b.points_required);
                break;
            case 'points-desc':
                sorted.sort((a, b) => b.points_required - a.points_required);
                break;
            case 'duration':
                sorted.sort((a, b) => a.duration_minutes - b.duration_minutes);
                break;
            case 'departure_time':
                sorted.sort((a, b) => a.departure_time.localeCompare(b.departure_time));
                break;
            default:
                // Default sort by points
                sorted.sort((a, b) => a.points_required - b.points_required);
        }
        
        return sorted;
    },
    
    /**
     * Get current filter values from UI
     */
    getFromUI() {
        return {
            program: document.getElementById('filterProgram')?.value || '',
            maxPoints: parseInt(document.getElementById('filterMaxPoints')?.value) || null,
            directOnly: document.getElementById('filterDirectOnly')?.checked || false,
            sortBy: document.getElementById('sortBy')?.value || 'points',
        };
    },
    
    /**
     * Extract unique airlines from results
     */
    getUniqueAirlines(flights) {
        const airlines = new Set();
        flights.forEach(f => airlines.add(f.airline));
        return Array.from(airlines).sort();
    },
    
    /**
     * Extract unique programs from results
     */
    getUniquePrograms(flights) {
        const programs = new Set();
        flights.forEach(f => programs.add(f.source_program));
        return Array.from(programs).sort();
    },
    
    /**
     * Get points range from results
     */
    getPointsRange(flights) {
        if (flights.length === 0) {
            return { min: 0, max: 0 };
        }
        
        const points = flights.map(f => f.points_required);
        return {
            min: Math.min(...points),
            max: Math.max(...points),
        };
    }
};
