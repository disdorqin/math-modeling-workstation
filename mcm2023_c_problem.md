# 2023 MCM Problem C: Urban Flood Prediction

## Background
Urban flooding is a growing concern worldwide as cities expand and climate change increases the frequency and intensity of extreme precipitation events. Accurate flood prediction models are essential for disaster preparedness, infrastructure planning, and public safety.

## Problem Statement

### Part A
Build a mathematical model to predict the water depth at various locations in an urban area given precipitation data and the characteristics of the urban drainage system. Your model should account for factors such as rainfall intensity, ground permeability, drainage capacity, and terrain elevation.

### Part B
Using your model from Part A, analyze how different urban planning scenarios affect flood risk. Consider factors such as the proportion of impervious surfaces, size and number of drainage channels and retention ponds, and elevation and topography of the urban area.

### Part C
Build a model that incorporates real-time sensor data (water level sensors, rainfall gauges) to provide dynamic flood predictions. Your model should update predictions as new sensor data arrives and provide early warnings for potential flooding.

### Part D
Develop a decision support tool for emergency managers that recommends evacuation routes and shelter locations based on your flood predictions. The tool should prioritize minimizing risk to human life and property.

## Data
- 30-day historical hourly precipitation data (mm)
- Land use classification map (residential, commercial, industrial, green space, water)
- Drainage system capacity data (30 catchment areas)
- Terrain elevation data (100x100 grid, meters above sea level)
- Sensor locations: 25 water level sensors, 15 rainfall gauges
