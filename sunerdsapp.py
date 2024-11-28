import sqlite3
from datetime import datetime
import math
import requests
import base64
from typing import Dict, List, Optional
from PIL import Image
import io
import json
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder

class SolarAudit:
    def __init__(self, db_path: str = "solar_audit.db", weather_api_key: str = None):
        self.conn = sqlite3.connect(db_path)
        self.weather_api_key = weather_api_key
        self.setup_database()
        
    def setup_database(self):
        """Initialize enhanced database tables"""
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS properties (
                id INTEGER PRIMARY KEY,
                address TEXT,
                latitude FLOAT,
                longitude FLOAT,
                timezone TEXT,
                roof_area FLOAT,
                roof_angle FLOAT,
                orientation TEXT,
                shading_factor FLOAT,
                created_at TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS measurements (
                id INTEGER PRIMARY KEY,
                property_id INTEGER,
                solar_irradiance FLOAT,
                temperature FLOAT,
                humidity FLOAT,
                cloud_cover FLOAT,
                timestamp TIMESTAMP,
                FOREIGN KEY (property_id) REFERENCES properties (id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS photos (
                id INTEGER PRIMARY KEY,
                property_id INTEGER,
                photo_type TEXT,
                photo_data BLOB,
                gps_latitude FLOAT,
                gps_longitude FLOAT,
                timestamp TIMESTAMP,
                notes TEXT,
                FOREIGN KEY (property_id) REFERENCES properties (id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS financial_data (
                id INTEGER PRIMARY KEY,
                property_id INTEGER,
                electricity_rate FLOAT,
                installation_cost_per_watt FLOAT,
                incentives FLOAT,
                financing_rate FLOAT,
                financing_term INTEGER,
                maintenance_cost_annual FLOAT,
                electricity_price_increase FLOAT,
                timestamp TIMESTAMP,
                FOREIGN KEY (property_id) REFERENCES properties (id)
            )
        ''')
        
        self.conn.commit()

    def get_location_data(self, address: str) -> Dict:
        """Get GPS coordinates and timezone for an address"""
        geolocator = Nominatim(user_agent="solar_audit_app")
        location = geolocator.geocode(address)
        
        if location:
            tf = TimezoneFinder()
            timezone = tf.timezone_at(lat=location.latitude, lng=location.longitude)
            
            return {
                "latitude": location.latitude,
                "longitude": location.longitude,
                "timezone": timezone
            }
        raise ValueError("Address not found")

    def add_property(self, address: str, roof_area: float, roof_angle: float, 
                    orientation: str, shading_factor: float) -> int:
        """Add a new property with location data"""
        location_data = self.get_location_data(address)
        
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO properties 
            (address, latitude, longitude, timezone, roof_area, roof_angle, 
             orientation, shading_factor, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (address, location_data["latitude"], location_data["longitude"],
              location_data["timezone"], roof_area, roof_angle, orientation,
              shading_factor, datetime.now()))
        
        self.conn.commit()
        return cursor.lastrowid

    def add_photo(self, property_id: int, photo_path: str, photo_type: str,
                 gps_latitude: float, gps_longitude: float, notes: str = None):
        """Add a photo with GPS data to the database"""
        with Image.open(photo_path) as img:
            # Resize image to reasonable size for storage
            max_size = (1024, 1024)
            img.thumbnail(max_size, Image.LANCZOS)
            
            # Convert to bytes
            buffer = io.BytesIO()
            img.save(buffer, format=img.format)
            photo_data = buffer.getvalue()
        
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO photos 
            (property_id, photo_type, photo_data, gps_latitude, gps_longitude, 
             timestamp, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (property_id, photo_type, photo_data, gps_latitude, gps_longitude,
              datetime.now(), notes))
        
        self.conn.commit()

    def get_weather_data(self, latitude: float, longitude: float) -> Dict:
        """Fetch current weather data from OpenWeatherMap API"""
        if not self.weather_api_key:
            raise ValueError("Weather API key not provided")
            
        url = f"http://api.openweathermap.org/data/2.5/weather?lat={latitude}&lon={longitude}&appid={self.weather_api_key}"
        response = requests.get(url)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "temperature": data["main"]["temp"] - 273.15,  # Convert K to C
                "humidity": data["main"]["humidity"],
                "cloud_cover": data["clouds"]["all"],
                "solar_irradiance": self.estimate_solar_irradiance(data["clouds"]["all"])
            }
        raise Exception("Failed to fetch weather data")

    def estimate_solar_irradiance(self, cloud_cover: float) -> float:
        """Estimate solar irradiance based on cloud cover"""
        # Basic estimation - can be improved with more sophisticated models
        max_irradiance = 1000  # W/m² on a clear day
        return max_irradiance * (1 - (cloud_cover / 100) * 0.75)

    def add_financial_data(self, property_id: int, electricity_rate: float,
                          installation_cost_per_watt: float, incentives: float = 0,
                          financing_rate: float = 0, financing_term: int = 0,
                          maintenance_cost_annual: float = 0,
                          electricity_price_increase: float = 0.03):
        """Add financial parameters for analysis"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO financial_data 
            (property_id, electricity_rate, installation_cost_per_watt, incentives,
             financing_rate, financing_term, maintenance_cost_annual,
             electricity_price_increase, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (property_id, electricity_rate, installation_cost_per_watt, incentives,
              financing_rate, financing_term, maintenance_cost_annual,
              electricity_price_increase, datetime.now()))
        
        self.conn.commit()

    def calculate_detailed_financials(self, property_id: int, years: int = 25) -> Dict:
        """Calculate detailed financial projections"""
        cursor = self.conn.cursor()
        
        # Get financial data
        cursor.execute('''
            SELECT * FROM financial_data 
            WHERE property_id = ? 
            ORDER BY timestamp DESC LIMIT 1
        ''', (property_id,))
        financial_data = cursor.fetchone()
        
        if not financial_data:
            raise ValueError("Financial data not found for property")
            
        # Get solar potential
        solar_potential = self.calculate_solar_potential(property_id)
        annual_production = solar_potential["annual_potential_kwh"]
        
        # System size and costs
        system_size_kw = annual_production / (365 * 4)  # Rough estimate
        base_cost = system_size_kw * 1000 * financial_data[2]  # installation_cost_per_watt
        net_cost = base_cost - financial_data[3]  # subtract incentives
        
        # Initialize arrays for year-by-year analysis
        yearly_analysis = []
        cumulative_savings = 0
        electricity_rate = financial_data[1]  # Starting electricity rate
        
        for year in range(1, years + 1):
            # Calculate degradation (0.5% per year)
            production = annual_production * (1 - 0.005 * year)
            
            # Calculate electricity savings
            savings = production * electricity_rate
            
            # Add maintenance cost
            net_savings = savings - financial_data[6]  # maintenance_cost_annual
            
            # Update cumulative savings
            cumulative_savings += net_savings
            
            # Calculate ROI
            roi = (cumulative_savings / net_cost) * 100 if net_cost > 0 else 0
            
            # Update electricity rate for next year
            electricity_rate *= (1 + financial_data[7])  # electricity_price_increase
            
            yearly_analysis.append({
                "year": year,
                "production_kwh": round(production, 2),
                "electricity_rate": round(electricity_rate, 3),
                "yearly_savings": round(net_savings, 2),
                "cumulative_savings": round(cumulative_savings, 2),
                "roi_percentage": round(roi, 2)
            })
        
        # Calculate financing if applicable
        financing_details = None
        if financial_data[4] > 0 and financial_data[5] > 0:  # if financing_rate and term exist
            monthly_rate = financial_data[4] / 12 / 100
            num_payments = financial_data[5] * 12
            monthly_payment = (net_cost * monthly_rate * (1 + monthly_rate)**num_payments) / ((1 + monthly_rate)**num_payments - 1)
            
            financing_details = {
                "monthly_payment": round(monthly_payment, 2),
                "total_payments": round(monthly_payment * num_payments, 2),
                "total_interest": round((monthly_payment * num_payments) - net_cost, 2)
            }
        
        return {
            "system_details": {
                "size_kw": round(system_size_kw, 2),
                "base_cost": round(base_cost, 2),
                "incentives": round(financial_data[3], 2),
                "net_cost": round(net_cost, 2)
            },
            "financing": financing_details,
            "yearly_analysis": yearly_analysis,
            "summary": {
                "total_25_year_savings": round(cumulative_savings, 2),
                "average_annual_savings": round(cumulative_savings / years, 2),
                "break_even_year": next((year["year"] for year in yearly_analysis 
                                      if year["cumulative_savings"] >= net_cost), None)
            }
        }

    def generate_comprehensive_report(self, property_id: int) -> Dict:
        """Generate a comprehensive audit report including all data"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM properties WHERE id = ?', (property_id,))
        property_data = cursor.fetchone()
        
        if not property_data:
            raise ValueError("Property not found")
        
        # Get weather data
        weather = self.get_weather_data(property_data[2], property_data[3])
        
        # Get photos
        cursor.execute('SELECT id, photo_type, timestamp, notes FROM photos WHERE property_id = ?', 
                      (property_id,))
        photos = cursor.fetchall()
        
        # Get all calculations
        solar_potential = self.calculate_solar_potential(property_id)
        financial_analysis = self.calculate_detailed_financials(property_id)
        
        return {
            "property_details": {
                "address": property_data[1],
                "coordinates": {
                    "latitude": property_data[2],
                    "longitude": property_data[3]
                },
                "timezone": property_data[4],
                "roof_specifications": {
                    "area": property_data[5],
                    "angle": property_data[6],
                    "orientation": property_data[7],
                    "shading_factor": property_data[8]
                }
            },
            "current_conditions": weather,
            "documentation": [{
                "photo_id": photo[0],
                "type": photo[1],
                "timestamp": photo[2],
                "notes": photo[3]
            } for photo in photos],
            "solar_potential": solar_potential,
            "financial_analysis": financial_analysis
        }

    def export_report_pdf(self, property_id: int, output_path: str):
        """Export report as PDF with charts and images"""
        # Note: Implementation would require additional libraries like reportlab
        # This is a placeholder for the feature
        pass

# Example usage
if __name__ == "__main__":
    # Initialize with Weather API key
    solar_audit = SolarAudit(weather_api_key="your_api_key_here")
    
    try:
        # Add a new property
        property_id = solar_audit.add_property(
            address="123 Sun Street, Solar City, SC 12345",
            roof_area=100.0,
            roof_angle=30.0,
            orientation="S",
            shading_factor=0.1
        )
        
        # Add financial data
        solar_audit.add_financial_data(
            property_id=property_id,
            electricity_rate=0.12,
            installation_cost_per_watt=2.75,
            incentives=5000,
            financing_rate=4.5,
            financing_term=20,
            maintenance_cost_annual=200,
            electricity_price_increase=0.03
        )
        
        # Generate comprehensive report
        report = solar_audit.generate_comprehensive_report(property_id)
        
        # Print key findings
        print(f"Solar Audit Report Summary for {report['property_details']['address']}")
        print("\nSystem Specifications:")
        print(f"System Size: {report['financial_analysis']['system_details']['size_kw']} kW")
        print(f"Net Cost: ${report['financial_analysis']['system_details']['net_cost']:,.2f}")
        
        print("\nFinancial Projections:")
        print(f"25-Year Savings: ${report['financial_analysis']['summary']['total_25_year_savings']:,.2f}")
        print(f"Break-even Year: {report['financial_analysis']['summary']['break_even_year']}")
        
        if report['financial_analysis']['financing']:
            print(f"\nMonthly Payment: ${report['financial_analysis']['financing']['monthly_payment']:,.2f}")
        
    except Exception as e:
        print(f"Error: {str(e)}")
    finally:
        solar_audit.close()
        