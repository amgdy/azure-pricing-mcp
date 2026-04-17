#!/usr/bin/env python3
"""
Azure Pricing MCP Server

A Model Context Protocol server that provides tools for querying Azure retail pricing.
Supports multiple transports: stdio, SSE, and Streamable HTTP for remote access.
"""

import argparse
import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlencode, quote

import os

import aiohttp
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Azure Retail Prices API configuration
AZURE_PRICING_BASE_URL = "https://prices.azure.com/api/retail/prices"
DEFAULT_API_VERSION = "2023-01-01-preview"
MAX_RESULTS_PER_REQUEST = 1000

class AzurePricingServer:
    """Azure Pricing MCP Server implementation."""
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    async def _make_request(self, url: str, params: Dict[str, Any] = None, max_retries: int = 3) -> Dict[str, Any]:
        """Make HTTP request to Azure Pricing API with retry logic for rate limiting."""
        if not self.session:
            raise RuntimeError("HTTP session not initialized")
        
        last_exception = None
        
        for attempt in range(max_retries + 1):  # 0, 1, 2, 3 (4 total attempts)
            try:
                async with self.session.get(url, params=params) as response:
                    if response.status == 429:  # Too Many Requests
                        if attempt < max_retries:
                            wait_time = 5 * (attempt + 1)  # 5, 10, 15 seconds
                            logger.warning(f"Rate limited (429). Retrying in {wait_time} seconds... (attempt {attempt + 1}/{max_retries + 1})")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            # Last attempt failed, raise the error
                            response.raise_for_status()
                    
                    response.raise_for_status()
                    return await response.json()
                    
            except aiohttp.ClientResponseError as e:
                if e.status == 429 and attempt < max_retries:
                    wait_time = 5 * (attempt + 1)
                    logger.warning(f"Rate limited (429). Retrying in {wait_time} seconds... (attempt {attempt + 1}/{max_retries + 1})")
                    await asyncio.sleep(wait_time)
                    last_exception = e
                    continue
                else:
                    logger.error(f"HTTP request failed: {e}")
                    raise
            except aiohttp.ClientError as e:
                logger.error(f"HTTP request failed: {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error during request: {e}")
                raise
        
        # If we get here, all retries failed
        if last_exception:
            raise last_exception
    
    async def search_azure_prices(
        self,
        service_name: Optional[str] = None,
        service_family: Optional[str] = None,
        region: Optional[str] = None,
        sku_name: Optional[str] = None,
        price_type: Optional[str] = None,
        currency_code: str = "USD",
        limit: int = 50,
        discount_percentage: Optional[float] = None,
        validate_sku: bool = True
    ) -> Dict[str, Any]:
        """Search Azure retail prices with various filters, SKU validation, and discount support."""
        
        # Build filter conditions
        filter_conditions = []
        
        if service_name:
            filter_conditions.append(f"serviceName eq '{service_name}'")
        if service_family:
            filter_conditions.append(f"serviceFamily eq '{service_family}'")
        if region:
            filter_conditions.append(f"armRegionName eq '{region}'")
        if sku_name:
            filter_conditions.append(f"contains(skuName, '{sku_name}')")
        if price_type:
            filter_conditions.append(f"priceType eq '{price_type}'")
        
        # Construct query parameters
        params = {
            "api-version": DEFAULT_API_VERSION,
            "currencyCode": currency_code
        }
        
        if filter_conditions:
            params["$filter"] = " and ".join(filter_conditions)
        
        # Limit results
        if limit < MAX_RESULTS_PER_REQUEST:
            params["$top"] = str(limit)
        
        # Make request
        data = await self._make_request(AZURE_PRICING_BASE_URL, params)
        
        # Process results
        items = data.get("Items", [])
        
        # If we have more results than requested, truncate
        if len(items) > limit:
            items = items[:limit]
        
        # SKU validation and clarification
        validation_info = {}
        if validate_sku and sku_name and not items:
            validation_info = await self._validate_and_suggest_skus(service_name, sku_name, currency_code)
        elif validate_sku and sku_name and isinstance(items, list) and len(items) > 10:
            # Too many results - provide clarification
            validation_info["clarification"] = {
                "message": f"Found {len(items)} SKUs matching '{sku_name}'. Consider being more specific.",
                "suggestions": [item.get("skuName") for item in items[:5] if item and item.get("skuName")]
            }
        
        # Apply discount if provided
        if discount_percentage is not None and discount_percentage > 0 and isinstance(items, list):
            items = self._apply_discount_to_items(items, discount_percentage)
        
        result = {
            "items": items,
            "count": len(items) if isinstance(items, list) else 0,
            "has_more": bool(data.get("NextPageLink")),
            "currency": currency_code,
            "filters_applied": filter_conditions
        }
        
        # Add discount info if applied
        if discount_percentage is not None and discount_percentage > 0:
            result["discount_applied"] = {
                "percentage": discount_percentage,
                "note": "Prices shown are after discount"
            }
        
        # Add validation info if available
        if validation_info:
            result.update(validation_info)
        
        return result
    
    async def _validate_and_suggest_skus(
        self,
        service_name: Optional[str],
        sku_name: str,
        currency_code: str = "USD"
    ) -> Dict[str, Any]:
        """Validate SKU name and suggest alternatives if not found."""
        
        # Try to find similar SKUs
        suggestions = []
        
        if service_name:
            # Search for SKUs within the service
            broad_search = await self.search_azure_prices(
                service_name=service_name,
                currency_code=currency_code,
                limit=100,
                validate_sku=False  # Avoid recursion
            )
            
            # Find SKUs that partially match
            sku_lower = sku_name.lower()
            items = broad_search.get("items", [])
            if items:  # Only process if items exist
                for item in items:
                    item_sku = item.get("skuName")
                    if not item_sku:  # Skip items without SKU names
                        continue
                    item_sku_lower = item_sku.lower()
                    if (sku_lower in item_sku_lower or 
                        item_sku_lower in sku_lower or
                        any(word in item_sku_lower for word in sku_lower.split() if word)):
                        suggestions.append({
                            "sku_name": item_sku,
                            "product_name": item.get("productName", "Unknown"),
                            "price": item.get("retailPrice", 0),
                            "unit": item.get("unitOfMeasure", "Unknown"),
                            "region": item.get("armRegionName", "Unknown")
                        })
        
        # Remove duplicates and limit suggestions
        seen_skus = set()
        unique_suggestions = []
        for suggestion in suggestions:
            sku = suggestion["sku_name"]
            if sku not in seen_skus:
                seen_skus.add(sku)
                unique_suggestions.append(suggestion)
                if len(unique_suggestions) >= 5:
                    break
        
        return {
            "sku_validation": {
                "original_sku": sku_name,
                "found": False,
                "message": f"SKU '{sku_name}' not found" + (f" in service '{service_name}'" if service_name else ""),
                "suggestions": unique_suggestions
            }
        }
    
    def _apply_discount_to_items(self, items: List[Dict], discount_percentage: float) -> List[Dict]:
        """Apply discount percentage to pricing items."""
        if not items:
            return []
        
        discounted_items = []
        
        for item in items:
            discounted_item = item.copy()
            
            # Apply discount to retail price
            if "retailPrice" in item and item["retailPrice"]:
                original_price = item["retailPrice"]
                discounted_price = original_price * (1 - discount_percentage / 100)
                discounted_item["retailPrice"] = round(discounted_price, 6)
                discounted_item["originalPrice"] = original_price
            
            # Apply discount to savings plans if present
            if "savingsPlan" in item and item["savingsPlan"] and isinstance(item["savingsPlan"], list):
                discounted_savings = []
                for plan in item["savingsPlan"]:
                    discounted_plan = plan.copy()
                    if "retailPrice" in plan and plan["retailPrice"]:
                        original_plan_price = plan["retailPrice"]
                        discounted_plan_price = original_plan_price * (1 - discount_percentage / 100)
                        discounted_plan["retailPrice"] = round(discounted_plan_price, 6)
                        discounted_plan["originalPrice"] = original_plan_price
                    discounted_savings.append(discounted_plan)
                discounted_item["savingsPlan"] = discounted_savings
            
            discounted_items.append(discounted_item)
        
        return discounted_items
    
    async def get_customer_discount(self, customer_id: Optional[str] = None) -> Dict[str, Any]:
        """Get customer discount information. Currently returns 10% default discount for all customers."""
        
        # For now, return a default 10% discount for all customers
        # In the future, this could be enhanced to query a customer database
        
        return {
            "customer_id": customer_id or "default",
            "discount_percentage": 10.0,
            "discount_type": "standard",
            "description": "Standard customer discount",
            "valid_until": None,  # No expiration for standard discount
            "applicable_services": "all",  # Applies to all Azure services
            "note": "This is a default discount applied to all customers. Contact sales for enterprise discounts."
        }
    
    async def compare_prices(
        self,
        service_name: str,
        sku_name: Optional[str] = None,
        regions: Optional[List[str]] = None,
        currency_code: str = "USD",
        discount_percentage: Optional[float] = None
    ) -> Dict[str, Any]:
        """Compare prices across different regions or SKUs."""
        
        comparisons = []
        
        if regions and isinstance(regions, list):
            # Compare across regions
            for region in regions:
                try:
                    result = await self.search_azure_prices(
                        service_name=service_name,
                        sku_name=sku_name,
                        region=region,
                        currency_code=currency_code,
                        limit=10
                    )
                    
                    if result["items"]:
                        # Get the first item for comparison
                        item = result["items"][0]
                        comparisons.append({
                            "region": region,
                            "sku_name": item.get("skuName"),
                            "retail_price": item.get("retailPrice"),
                            "unit_of_measure": item.get("unitOfMeasure"),
                            "product_name": item.get("productName"),
                            "meter_name": item.get("meterName")
                        })
                except Exception as e:
                    logger.warning(f"Failed to get prices for region {region}: {e}")
        else:
            # Compare different SKUs within the same service
            result = await self.search_azure_prices(
                service_name=service_name,
                currency_code=currency_code,
                limit=20
            )
            
            # Group by SKU
            sku_prices = {}
            items = result.get("items", [])
            for item in items:
                sku = item.get("skuName")
                if sku and sku not in sku_prices:
                    sku_prices[sku] = {
                        "sku_name": sku,
                        "retail_price": item.get("retailPrice"),
                        "unit_of_measure": item.get("unitOfMeasure"),
                        "product_name": item.get("productName"),
                        "region": item.get("armRegionName"),
                        "meter_name": item.get("meterName")
                    }
            
            comparisons = list(sku_prices.values())
        
        # Apply discount if provided
        if discount_percentage is not None and discount_percentage > 0:
            for comparison in comparisons:
                if "retail_price" in comparison and comparison["retail_price"]:
                    original_price = comparison["retail_price"]
                    discounted_price = original_price * (1 - discount_percentage / 100)
                    comparison["retail_price"] = round(discounted_price, 6)
                    comparison["original_price"] = original_price
        
        # Sort by price
        comparisons.sort(key=lambda x: x.get("retail_price", 0))
        
        result = {
            "comparisons": comparisons,
            "service_name": service_name,
            "currency": currency_code,
            "comparison_type": "regions" if regions else "skus"
        }
        
        # Add discount info if applied
        if discount_percentage is not None and discount_percentage > 0:
            result["discount_applied"] = {
                "percentage": discount_percentage,
                "note": "Prices shown are after discount"
            }
        
        return result
    
    async def estimate_costs(
        self,
        service_name: str,
        sku_name: str,
        region: str,
        hours_per_month: float = 730,  # Default to full month
        currency_code: str = "USD",
        discount_percentage: Optional[float] = None
    ) -> Dict[str, Any]:
        """Estimate monthly costs based on usage."""
        
        # Get pricing information
        result = await self.search_azure_prices(
            service_name=service_name,
            sku_name=sku_name,
            region=region,
            currency_code=currency_code,
            limit=5
        )
        
        if not result["items"]:
            return {
                "error": f"No pricing found for {sku_name} in {region}",
                "service_name": service_name,
                "sku_name": sku_name,
                "region": region
            }
        
        item = result["items"][0]
        hourly_rate = item.get("retailPrice", 0)
        
        # Apply discount if provided
        if discount_percentage is not None and discount_percentage > 0:
            original_hourly_rate = hourly_rate
            hourly_rate = hourly_rate * (1 - discount_percentage / 100)
        
        # Calculate estimates
        monthly_cost = hourly_rate * hours_per_month
        daily_cost = hourly_rate * 24
        yearly_cost = monthly_cost * 12
        
        # Check for savings plans
        savings_plans = item.get("savingsPlan", [])
        savings_estimates = []
        
        for plan in savings_plans:
            plan_hourly = plan.get("retailPrice", 0)
            
            # Apply discount to savings plan prices too
            if discount_percentage is not None and discount_percentage > 0:
                original_plan_hourly = plan_hourly
                plan_hourly = plan_hourly * (1 - discount_percentage / 100)
            
            plan_monthly = plan_hourly * hours_per_month
            plan_yearly = plan_monthly * 12
            savings_percent = ((hourly_rate - plan_hourly) / hourly_rate) * 100 if hourly_rate > 0 else 0
            
            plan_data = {
                "term": plan.get("term"),
                "hourly_rate": round(plan_hourly, 6),
                "monthly_cost": round(plan_monthly, 2),
                "yearly_cost": round(plan_yearly, 2),
                "savings_percent": round(savings_percent, 2),
                "annual_savings": round((yearly_cost - plan_yearly), 2)
            }
            
            # Add original prices if discount was applied
            if discount_percentage is not None and discount_percentage > 0:
                plan_data["original_hourly_rate"] = original_plan_hourly
                plan_data["original_monthly_cost"] = round(original_plan_hourly * hours_per_month, 2)
                plan_data["original_yearly_cost"] = round(original_plan_hourly * hours_per_month * 12, 2)
            
            savings_estimates.append(plan_data)
        
        result = {
            "service_name": service_name,
            "sku_name": item.get("skuName"),
            "region": region,
            "product_name": item.get("productName"),
            "unit_of_measure": item.get("unitOfMeasure"),
            "currency": currency_code,
            "on_demand_pricing": {
                "hourly_rate": round(hourly_rate, 6),
                "daily_cost": round(daily_cost, 2),
                "monthly_cost": round(monthly_cost, 2),
                "yearly_cost": round(yearly_cost, 2)
            },
            "usage_assumptions": {
                "hours_per_month": hours_per_month,
                "hours_per_day": round(hours_per_month / 30.44, 2)  # Average days per month
            },
            "savings_plans": savings_estimates
        }
        
        # Add discount info and original prices if discount was applied
        if discount_percentage is not None and discount_percentage > 0:
            result["discount_applied"] = {
                "percentage": discount_percentage,
                "note": "All prices shown are after discount"
            }
            result["on_demand_pricing"]["original_hourly_rate"] = original_hourly_rate
            result["on_demand_pricing"]["original_daily_cost"] = round(original_hourly_rate * 24, 2)
            result["on_demand_pricing"]["original_monthly_cost"] = round(original_hourly_rate * hours_per_month, 2)
            result["on_demand_pricing"]["original_yearly_cost"] = round(original_hourly_rate * hours_per_month * 12, 2)
        
        return result

    async def discover_skus(
        self,
        service_name: str,
        region: Optional[str] = None,
        price_type: str = "Consumption",
        limit: int = 100
    ) -> Dict[str, Any]:
        """Discover available SKUs for a specific Azure service."""
        
        # Build filter conditions
        filter_conditions = [f"serviceName eq '{service_name}'"]
        
        if region:
            filter_conditions.append(f"armRegionName eq '{region}'")
        
        if price_type:
            filter_conditions.append(f"priceType eq '{price_type}'")
        
        # Construct query parameters
        params = {
            "api-version": DEFAULT_API_VERSION,
            "currencyCode": "USD"
        }
        
        if filter_conditions:
            params["$filter"] = " and ".join(filter_conditions)
        
        # Limit results
        if limit < MAX_RESULTS_PER_REQUEST:
            params["$top"] = str(limit)
        
        # Make request
        data = await self._make_request(AZURE_PRICING_BASE_URL, params)
        
        # Process and deduplicate SKUs
        skus = {}
        items = data.get("Items", [])
        
        for item in items:
            sku_name = item.get("skuName")
            arm_sku_name = item.get("armSkuName")
            product_name = item.get("productName")
            region = item.get("armRegionName")
            price = item.get("retailPrice", 0)
            unit = item.get("unitOfMeasure")
            meter_name = item.get("meterName")
            
            if sku_name and sku_name not in skus:
                skus[sku_name] = {
                    "sku_name": sku_name,
                    "arm_sku_name": arm_sku_name,
                    "product_name": product_name,
                    "sample_price": price,
                    "unit_of_measure": unit,
                    "meter_name": meter_name,
                    "sample_region": region,
                    "available_regions": [region] if region else []
                }
            elif sku_name and region and region not in skus[sku_name]["available_regions"]:
                # Add region to existing SKU
                skus[sku_name]["available_regions"].append(region)
        
        # Convert to list and sort by SKU name
        sku_list = list(skus.values())
        sku_list.sort(key=lambda x: x["sku_name"])
        
        return {
            "service_name": service_name,
            "skus": sku_list,
            "total_skus": len(sku_list),
            "price_type": price_type,
            "region_filter": region
        }

    async def search_azure_prices_with_fuzzy_matching(
        self,
        service_name: Optional[str] = None,
        service_family: Optional[str] = None,
        region: Optional[str] = None,
        sku_name: Optional[str] = None,
        price_type: Optional[str] = None,
        currency_code: str = "USD",
        limit: int = 50,
        suggest_alternatives: bool = True
    ) -> Dict[str, Any]:
        """
        Search Azure retail prices with fuzzy matching and suggestions.
        If exact matches aren't found, suggests similar services.
        """
        
        # First try exact search
        exact_result = await self.search_azure_prices(
            service_name=service_name,
            service_family=service_family,
            region=region,
            sku_name=sku_name,
            price_type=price_type,
            currency_code=currency_code,
            limit=limit
        )
        
        # If we got results, return them
        if exact_result["items"]:
            return exact_result
        
        # If no results and suggest_alternatives is True, try fuzzy matching
        if suggest_alternatives and (service_name or service_family):
            return await self._find_similar_services(
                service_name=service_name,
                service_family=service_family,
                currency_code=currency_code,
                limit=limit
            )
        
        return exact_result
    
    async def _find_similar_services(
        self,
        service_name: Optional[str] = None,
        service_family: Optional[str] = None,
        currency_code: str = "USD",
        limit: int = 50
    ) -> Dict[str, Any]:
        """Find services with similar names or suggest alternatives."""
        
        # Common service name mappings
        service_mappings = {
            # User input -> Correct Azure service name
            "app service": "Azure App Service",
            "web app": "Azure App Service",
            "web apps": "Azure App Service",
            "app services": "Azure App Service",
            "websites": "Azure App Service",
            "web service": "Azure App Service",
            
            "virtual machine": "Virtual Machines",
            "vm": "Virtual Machines",
            "vms": "Virtual Machines",
            "compute": "Virtual Machines",
            
            "storage": "Storage",
            "blob": "Storage",
            "blob storage": "Storage",
            "file storage": "Storage",
            "disk": "Storage",
            
            "sql": "Azure SQL Database",
            "sql database": "Azure SQL Database",
            "database": "Azure SQL Database",
            "sql server": "Azure SQL Database",
            
            "cosmos": "Azure Cosmos DB",
            "cosmosdb": "Azure Cosmos DB",
            "cosmos db": "Azure Cosmos DB",
            "document db": "Azure Cosmos DB",
            
            "kubernetes": "Azure Kubernetes Service",
            "aks": "Azure Kubernetes Service",
            "k8s": "Azure Kubernetes Service",
            "container service": "Azure Kubernetes Service",
            
            "functions": "Azure Functions",
            "function app": "Azure Functions",
            "serverless": "Azure Functions",
            
            "redis": "Azure Cache for Redis",
            "cache": "Azure Cache for Redis",
            
            "ai": "Azure AI services",
            "cognitive": "Azure AI services",
            "cognitive services": "Azure AI services",
            "openai": "Azure OpenAI",
            
            "networking": "Virtual Network",
            "network": "Virtual Network",
            "vnet": "Virtual Network",
            
            "load balancer": "Load Balancer",
            "lb": "Load Balancer",
            
            "application gateway": "Application Gateway",
            "app gateway": "Application Gateway",
        }
        
        suggestions = []
        search_term = service_name.lower() if service_name else ""
        
        # Try exact mapping first
        if search_term in service_mappings:
            correct_name = service_mappings[search_term]
            result = await self.search_azure_prices(
                service_name=correct_name,
                currency_code=currency_code,
                limit=limit
            )
            
            if result["items"]:
                result["suggestion_used"] = correct_name
                result["original_search"] = service_name
                result["match_type"] = "exact_mapping"
                return result
        
        # Try partial matching for common terms
        partial_matches = []
        for user_term, azure_service in service_mappings.items():
            if search_term in user_term or user_term in search_term:
                partial_matches.append(azure_service)
        
        # Remove duplicates and try each match
        for azure_service in list(set(partial_matches)):
            result = await self.search_azure_prices(
                service_name=azure_service,
                currency_code=currency_code,
                limit=5
            )
            
            if result["items"]:
                suggestions.append({
                    "service_name": azure_service,
                    "match_reason": f"Partial match for '{service_name}'",
                    "sample_items": result["items"][:3]
                })
        
        # If still no matches, do a broad search and look for similar services
        if not suggestions:
            broad_result = await self.search_azure_prices(
                service_family=service_family,
                currency_code=currency_code,
                limit=100
            )
            
            # Find services that contain the search term
            matching_services = set()
            for item in broad_result.get("items", []):
                service = item.get("serviceName", "")
                product = item.get("productName", "")
                
                if (search_term in service.lower() or 
                    search_term in product.lower() or
                    any(word in service.lower() for word in search_term.split())):
                    matching_services.add(service)
            
            # Create suggestions from found services
            for service in list(matching_services)[:5]:  # Limit to top 5
                service_result = await self.search_azure_prices(
                    service_name=service,
                    currency_code=currency_code,
                    limit=3
                )
                
                if service_result["items"]:
                    suggestions.append({
                        "service_name": service,
                        "match_reason": f"Contains '{search_term}'",
                        "sample_items": service_result["items"][:2]
                    })
        
        return {
            "items": [],
            "count": 0,
            "has_more": False,
            "currency": currency_code,
            "original_search": service_name or service_family,
            "suggestions": suggestions,
            "match_type": "suggestions_only"
        }
    
    async def discover_service_skus(
        self,
        service_hint: str,
        region: Optional[str] = None,
        currency_code: str = "USD",
        limit: int = 30
    ) -> Dict[str, Any]:
        """
        Discover SKUs for a service with intelligent service name matching.
        
        Args:
            service_hint: User's description of the service (e.g., "app service", "web app")
            region: Optional specific region to filter by
            currency_code: Currency for pricing
            limit: Maximum number of results
        """
        
        # Use fuzzy matching to find the right service
        result = await self.search_azure_prices_with_fuzzy_matching(
            service_name=service_hint,
            region=region,
            currency_code=currency_code,
            limit=limit
        )
        
        # If we found exact matches, process SKUs
        if result["items"]:
            skus = {}
            service_used = result.get("suggestion_used", service_hint)
            
            for item in result["items"]:
                sku_name = item.get("skuName", "Unknown")
                arm_sku = item.get("armSkuName", "Unknown")
                product = item.get("productName", "Unknown")
                price = item.get("retailPrice", 0)
                unit = item.get("unitOfMeasure", "Unknown")
                item_region = item.get("armRegionName", "Unknown")
                
                if sku_name not in skus:
                    skus[sku_name] = {
                        "sku_name": sku_name,
                        "arm_sku_name": arm_sku,
                        "product_name": product,
                        "prices": [],
                        "regions": set()
                    }
                
                skus[sku_name]["prices"].append({
                    "price": price,
                    "unit": unit,
                    "region": item_region
                })
                skus[sku_name]["regions"].add(item_region)
            
            # Convert sets to lists for JSON serialization
            for sku_data in skus.values():
                sku_data["regions"] = list(sku_data["regions"])
                # Keep only the cheapest price for summary - handle empty sequences
                valid_prices = [p["price"] for p in sku_data["prices"] if p["price"] > 0]
                if valid_prices:
                    sku_data["min_price"] = min(valid_prices)
                else:
                    # If no valid prices > 0, use the first price (even if 0) or default to 0
                    sku_data["min_price"] = sku_data["prices"][0]["price"] if sku_data["prices"] else 0
                sku_data["sample_unit"] = sku_data["prices"][0]["unit"] if sku_data["prices"] else "Unknown"
            
            return {
                "service_found": service_used,
                "original_search": service_hint,
                "skus": skus,
                "total_skus": len(skus),
                "currency": currency_code,
                "match_type": result.get("match_type", "exact")
            }
        
        # If no exact matches, return suggestions
        return {
            "service_found": None,
            "original_search": service_hint,
            "skus": {},
            "total_skus": 0,
            "currency": currency_code,
            "suggestions": result.get("suggestions", []),
            "match_type": "no_match"
        }

# Create the FastMCP server with remote transport support
# Note: Default host is 127.0.0.1 (localhost only) for security.
# Use --host 0.0.0.0 to expose to all network interfaces when deploying
# behind a reverse proxy or in a trusted network environment.

# Configure transport security for DNS rebinding protection.
# When deployed behind a reverse proxy or cloud platform (e.g. Azure Container Apps),
# the Host header will be the external domain, not localhost. We need to either:
# - Disable DNS rebinding protection (the platform handles host validation), or
# - Explicitly list allowed hosts via the MCP_ALLOWED_HOSTS environment variable.
# See: https://github.com/modelcontextprotocol/python-sdk/issues/1798
_allowed_hosts_env = os.environ.get("MCP_ALLOWED_HOSTS", "")
if _allowed_hosts_env:
    _transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[h.strip() for h in _allowed_hosts_env.split(",") if h.strip()],
    )
else:
    _transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    )

mcp = FastMCP(
    "azure-pricing",
    instructions="Azure Pricing MCP Server - Query Azure retail pricing information using the Azure Retail Prices API. "
    "Supports price search, comparison, cost estimation, and SKU discovery.",
    host="127.0.0.1",
    port=8000,
    streamable_http_path="/mcp",
    transport_security=_transport_security,
)

# Global server instance
pricing_server = AzurePricingServer()


# --- Tool definitions using FastMCP decorators ---


@mcp.tool()
async def azure_price_search(
    service_name: Optional[str] = None,
    service_family: Optional[str] = None,
    region: Optional[str] = None,
    sku_name: Optional[str] = None,
    price_type: Optional[str] = None,
    currency_code: str = "USD",
    limit: int = 50,
    discount_percentage: Optional[float] = None,
    validate_sku: bool = True,
) -> str:
    """Search Azure retail prices with various filters.

    Args:
        service_name: Azure service name (e.g., 'Virtual Machines', 'Storage')
        service_family: Service family (e.g., 'Compute', 'Storage', 'Networking')
        region: Azure region (e.g., 'eastus', 'westeurope')
        sku_name: SKU name to search for (partial matches supported)
        price_type: Price type: 'Consumption', 'Reservation', or 'DevTestConsumption'
        currency_code: Currency code (default: USD)
        limit: Maximum number of results (default: 50)
        discount_percentage: Discount percentage to apply to prices (e.g., 10 for 10% discount)
        validate_sku: Whether to validate SKU names and provide suggestions (default: true)
    """
    try:
        async with pricing_server:
            # Always get customer discount and apply it
            customer_discount = await pricing_server.get_customer_discount()
            default_discount = customer_discount["discount_percentage"]

            # Use provided discount or default customer discount
            if discount_percentage is None:
                discount_percentage = default_discount

            result = await pricing_server.search_azure_prices(
                service_name=service_name,
                service_family=service_family,
                region=region,
                sku_name=sku_name,
                price_type=price_type,
                currency_code=currency_code,
                limit=limit,
                discount_percentage=discount_percentage,
                validate_sku=validate_sku,
            )

            # Format the response
            if result["items"]:
                formatted_items = []
                for item in result["items"]:
                    formatted_item = {
                        "service": item.get("serviceName"),
                        "product": item.get("productName"),
                        "sku": item.get("skuName"),
                        "region": item.get("armRegionName"),
                        "location": item.get("location"),
                        "discounted_price": item.get("retailPrice"),
                        "unit": item.get("unitOfMeasure"),
                        "type": item.get("type"),
                        "savings_plans": item.get("savingsPlan", []),
                    }

                    # Add original price and savings if discount was applied
                    if "originalPrice" in item:
                        original_price = item["originalPrice"]
                        discounted_price = item["retailPrice"]
                        savings_amount = original_price - discounted_price

                        formatted_item["original_price"] = original_price
                        formatted_item["savings_amount"] = round(savings_amount, 6)
                        formatted_item["savings_percentage"] = (
                            round((savings_amount / original_price * 100), 2)
                            if original_price > 0
                            else 0
                        )

                    formatted_items.append(formatted_item)

                if result["count"] > 0:
                    response_text = f"Found {result['count']} Azure pricing results:\n\n"

                    # Add discount information if applied
                    if "discount_applied" in result:
                        response_text += f"💰 **Customer Discount Applied: {result['discount_applied']['percentage']}%**\n"
                        response_text += (
                            f"   {result['discount_applied']['note']}\n\n"
                        )

                    # Add SKU validation info if present
                    if "sku_validation" in result:
                        validation = result["sku_validation"]
                        response_text += (
                            f"⚠️ SKU Validation: {validation['message']}\n"
                        )
                        if validation["suggestions"]:
                            response_text += "🔍 Suggested SKUs:\n"
                            for suggestion in validation["suggestions"][:3]:
                                response_text += f"   • {suggestion['sku_name']}: ${suggestion['price']} per {suggestion['unit']}\n"
                            response_text += "\n"

                    # Add clarification info if present
                    if "clarification" in result:
                        clarification = result["clarification"]
                        response_text += f"ℹ️ {clarification['message']}\n"
                        if clarification["suggestions"]:
                            response_text += "Top matches:\n"
                            for suggestion in clarification["suggestions"]:
                                response_text += f"   • {suggestion}\n"
                            response_text += "\n"

                    # Add summary of savings if discount was applied
                    if "discount_applied" in result:
                        total_original_cost = sum(
                            item.get("original_price", 0) for item in formatted_items
                        )
                        total_discounted_cost = sum(
                            item.get("discounted_price", 0) for item in formatted_items
                        )
                        total_savings = total_original_cost - total_discounted_cost

                        if total_savings > 0:
                            response_text += "💰 **Total Savings Summary:**\n"
                            response_text += (
                                f"   Original Total: ${total_original_cost:.6f}\n"
                            )
                            response_text += f"   Discounted Total: ${total_discounted_cost:.6f}\n"
                            response_text += (
                                f"   **You Save: ${total_savings:.6f}**\n\n"
                            )

                    response_text += "**Detailed Pricing:**\n"
                    response_text += json.dumps(formatted_items, indent=2)

                    return response_text
                else:
                    return "No valid pricing results found."
            else:
                response_text = (
                    "No pricing results found for the specified criteria."
                )

                # Show discount info even when no results
                if "discount_applied" in result:
                    response_text += f"\n\n💰 Note: Your {result['discount_applied']['percentage']}% customer discount would have been applied to any results."

                # Add SKU validation info if present
                if "sku_validation" in result:
                    validation = result["sku_validation"]
                    response_text += f"\n\n⚠️ {validation['message']}\n"
                    if validation["suggestions"]:
                        response_text += "\n🔍 Did you mean one of these SKUs?\n"
                        for suggestion in validation["suggestions"][:5]:
                            response_text += f"   • {suggestion['sku_name']}: ${suggestion['price']} per {suggestion['unit']}"
                            if suggestion["region"]:
                                response_text += f" (in {suggestion['region']})"
                            response_text += "\n"

                return response_text
    except Exception as e:
        logger.error(f"Error in azure_price_search: {e}")
        return f"Error: {str(e)}"


@mcp.tool()
async def azure_price_compare(
    service_name: str,
    sku_name: Optional[str] = None,
    regions: Optional[List[str]] = None,
    currency_code: str = "USD",
    discount_percentage: Optional[float] = None,
) -> str:
    """Compare Azure prices across regions or SKUs.

    Args:
        service_name: Azure service name to compare
        sku_name: Specific SKU to compare (optional)
        regions: List of regions to compare (if not provided, compares SKUs)
        currency_code: Currency code (default: USD)
        discount_percentage: Discount percentage to apply to prices (e.g., 10 for 10% discount)
    """
    try:
        async with pricing_server:
            result = await pricing_server.compare_prices(
                service_name=service_name,
                sku_name=sku_name,
                regions=regions,
                currency_code=currency_code,
                discount_percentage=discount_percentage,
            )

            response_text = f"Price comparison for {result['service_name']}:\n\n"

            # Add discount information if applied
            if "discount_applied" in result:
                response_text += f"💰 {result['discount_applied']['percentage']}% discount applied - {result['discount_applied']['note']}\n\n"

            response_text += json.dumps(result["comparisons"], indent=2)

            return response_text
    except Exception as e:
        logger.error(f"Error in azure_price_compare: {e}")
        return f"Error: {str(e)}"


@mcp.tool()
async def azure_cost_estimate(
    service_name: str,
    sku_name: str,
    region: str,
    hours_per_month: float = 730,
    currency_code: str = "USD",
    discount_percentage: Optional[float] = None,
) -> str:
    """Estimate Azure costs based on usage patterns.

    Args:
        service_name: Azure service name
        sku_name: SKU name
        region: Azure region
        hours_per_month: Expected hours of usage per month (default: 730 for full month)
        currency_code: Currency code (default: USD)
        discount_percentage: Discount percentage to apply to prices (e.g., 10 for 10% discount)
    """
    try:
        async with pricing_server:
            result = await pricing_server.estimate_costs(
                service_name=service_name,
                sku_name=sku_name,
                region=region,
                hours_per_month=hours_per_month,
                currency_code=currency_code,
                discount_percentage=discount_percentage,
            )

            if "error" in result:
                return f"Error: {result['error']}"

            # Format cost estimate
            estimate_text = f"""
Cost Estimate for {result['service_name']} - {result['sku_name']}
Region: {result['region']}
Product: {result['product_name']}
Unit: {result['unit_of_measure']}
Currency: {result['currency']}
"""

            # Add discount information if applied
            if "discount_applied" in result:
                estimate_text += f"\n💰 {result['discount_applied']['percentage']}% discount applied - {result['discount_applied']['note']}\n"

            estimate_text += f"""
Usage Assumptions:
- Hours per month: {result['usage_assumptions']['hours_per_month']}
- Hours per day: {result['usage_assumptions']['hours_per_day']}

On-Demand Pricing:
- Hourly Rate: ${result['on_demand_pricing']['hourly_rate']}
- Daily Cost: ${result['on_demand_pricing']['daily_cost']}
- Monthly Cost: ${result['on_demand_pricing']['monthly_cost']}
- Yearly Cost: ${result['on_demand_pricing']['yearly_cost']}
"""

            # Add original pricing if discount was applied
            if "discount_applied" in result and "original_hourly_rate" in result["on_demand_pricing"]:
                estimate_text += f"""
Original Pricing (before discount):
- Hourly Rate: ${result['on_demand_pricing']['original_hourly_rate']}
- Daily Cost: ${result['on_demand_pricing']['original_daily_cost']}
- Monthly Cost: ${result['on_demand_pricing']['original_monthly_cost']}
- Yearly Cost: ${result['on_demand_pricing']['original_yearly_cost']}
"""

            if result["savings_plans"]:
                estimate_text += "\nSavings Plans Available:\n"
                for plan in result["savings_plans"]:
                    estimate_text += f"""
{plan['term']} Term:
- Hourly Rate: ${plan['hourly_rate']}
- Monthly Cost: ${plan['monthly_cost']}
- Yearly Cost: ${plan['yearly_cost']}
- Savings: {plan['savings_percent']}% (${plan['annual_savings']} annually)
"""
                    # Add original pricing for savings plans if discount was applied
                    if "original_hourly_rate" in plan:
                        estimate_text += f"""- Original Hourly Rate: ${plan['original_hourly_rate']}
- Original Monthly Cost: ${plan['original_monthly_cost']}
- Original Yearly Cost: ${plan['original_yearly_cost']}
"""

            return estimate_text
    except Exception as e:
        logger.error(f"Error in azure_cost_estimate: {e}")
        return f"Error: {str(e)}"


@mcp.tool()
async def azure_discover_skus(
    service_name: str,
    region: Optional[str] = None,
    price_type: str = "Consumption",
    limit: int = 100,
) -> str:
    """Discover available SKUs for a specific Azure service.

    Args:
        service_name: Azure service name
        region: Azure region (optional)
        price_type: Price type (default: 'Consumption')
        limit: Maximum number of SKUs to return (default: 100)
    """
    try:
        async with pricing_server:
            result = await pricing_server.discover_skus(
                service_name=service_name,
                region=region,
                price_type=price_type,
                limit=limit,
            )

            # Format the response
            skus = result.get("skus", [])
            if skus:
                return (
                    f"Found {result['total_skus']} SKUs for {result['service_name']}:\n\n"
                    + json.dumps(skus, indent=2)
                )
            else:
                return "No SKUs found for the specified service."
    except Exception as e:
        logger.error(f"Error in azure_discover_skus: {e}")
        return f"Error: {str(e)}"


@mcp.tool()
async def azure_sku_discovery(
    service_hint: str,
    region: Optional[str] = None,
    currency_code: str = "USD",
    limit: int = 30,
) -> str:
    """Discover available SKUs for Azure services with intelligent name matching.

    Args:
        service_hint: Service name or description (e.g., 'app service', 'web app', 'vm', 'storage'). Supports fuzzy matching.
        region: Optional Azure region to filter results
        currency_code: Currency code (default: USD)
        limit: Maximum number of results (default: 30)
    """
    try:
        async with pricing_server:
            result = await pricing_server.discover_service_skus(
                service_hint=service_hint,
                region=region,
                currency_code=currency_code,
                limit=limit,
            )

            if result["service_found"]:
                # Format successful SKU discovery
                service_name = result["service_found"]
                original_search = result["original_search"]
                skus = result["skus"]
                total_skus = result["total_skus"]
                match_type = result.get("match_type", "exact")

                response_text = f"SKU Discovery for '{original_search}'"

                if match_type == "exact_mapping":
                    response_text += f" (mapped to: {service_name})"

                response_text += (
                    f"\n\nFound {total_skus} SKUs for {service_name}:\n\n"
                )

                # Group SKUs by product
                products = {}
                for sku_name_key, sku_data in skus.items():
                    product = sku_data["product_name"]
                    if product not in products:
                        products[product] = []
                    products[product].append((sku_name_key, sku_data))

                for product, product_skus in products.items():
                    response_text += f"📦 {product}:\n"
                    for sku_name_key, sku_data in sorted(product_skus)[
                        :10
                    ]:  # Limit to 10 per product
                        min_price = sku_data.get("min_price", 0)
                        unit = sku_data.get("sample_unit", "Unknown")
                        region_count = len(sku_data.get("regions", []))

                        response_text += f"   • {sku_name_key}\n"
                        response_text += f"     Price: ${min_price} per {unit}"
                        if region_count > 1:
                            response_text += (
                                f" (available in {region_count} regions)"
                            )
                        response_text += "\n"
                    response_text += "\n"

                return response_text
            else:
                # Format suggestions when no exact match
                suggestions = result.get("suggestions", [])
                original_search = result["original_search"]

                if suggestions:
                    response_text = (
                        f"No exact match found for '{original_search}'\n\n"
                    )
                    response_text += "🔍 Did you mean one of these services?\n\n"

                    for i, suggestion in enumerate(suggestions[:5], 1):
                        service_name = suggestion["service_name"]
                        match_reason = suggestion["match_reason"]
                        sample_items = suggestion["sample_items"]

                        response_text += f"{i}. {service_name}\n"
                        response_text += f"   Reason: {match_reason}\n"

                        if sample_items:
                            response_text += "   Sample SKUs:\n"
                            for item in sample_items[:3]:
                                sku = item.get("skuName", "Unknown")
                                price = item.get("retailPrice", 0)
                                unit = item.get("unitOfMeasure", "Unknown")
                                response_text += (
                                    f"     • {sku}: ${price} per {unit}\n"
                                )
                        response_text += "\n"

                    response_text += (
                        "💡 Try using one of the exact service names above."
                    )
                else:
                    response_text = (
                        f"No matches found for '{original_search}'\n\n"
                    )
                    response_text += "💡 Try using terms like:\n"
                    response_text += (
                        "• 'app service' or 'web app' for Azure App Service\n"
                    )
                    response_text += (
                        "• 'vm' or 'virtual machine' for Virtual Machines\n"
                    )
                    response_text += (
                        "• 'storage' or 'blob' for Storage services\n"
                    )
                    response_text += (
                        "• 'sql' or 'database' for SQL Database\n"
                    )
                    response_text += "• 'kubernetes' or 'aks' for Azure Kubernetes Service"

                return response_text
    except Exception as e:
        logger.error(f"Error in azure_sku_discovery: {e}")
        return f"Error: {str(e)}"


@mcp.tool()
async def get_customer_discount(
    customer_id: Optional[str] = None,
) -> str:
    """Get customer discount information. Returns default 10% discount for all customers.

    Args:
        customer_id: Customer ID (optional, defaults to 'default' customer)
    """
    try:
        async with pricing_server:
            result = await pricing_server.get_customer_discount(
                customer_id=customer_id
            )

            response_text = f"""Customer Discount Information

Customer ID: {result['customer_id']}
Discount Type: {result['discount_type']}
Discount Percentage: {result['discount_percentage']}%
Description: {result['description']}
Applicable Services: {result['applicable_services']}

{result['note']}
"""

            return response_text
    except Exception as e:
        logger.error(f"Error in get_customer_discount: {e}")
        return f"Error: {str(e)}"


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Azure Pricing MCP Server - supports stdio, SSE, and Streamable HTTP transports"
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http", "all"],
        default="streamable-http",
        help="Transport protocol to use (default: streamable-http). "
        "Use 'all' to serve both SSE and Streamable HTTP simultaneously.",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind to for HTTP transports (default: 127.0.0.1). Use 0.0.0.0 to expose to all interfaces.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to for HTTP transports (default: 8000)",
    )
    return parser.parse_args()


def _run_all_transports(host: str, port: int):
    """Run SSE, Streamable HTTP, and a test UI on a single server.

    This creates a combined Starlette application that serves:
      - /         -> Test UI (HTML page to exercise all MCP tools)
      - /mcp      -> Streamable HTTP transport (recommended for MCP clients)
      - /sse      -> SSE transport (legacy/backward compatibility)
      - /messages -> SSE message handling
    """
    import uvicorn
    from pathlib import Path
    from starlette.applications import Starlette
    from starlette.responses import HTMLResponse
    from starlette.routing import Route

    # Get the Starlette sub-apps from FastMCP.
    streamable_app = mcp.streamable_http_app()
    sse_app = mcp.sse_app()

    # Load the test UI HTML
    ui_path = Path(__file__).parent / "static" / "index.html"
    _ui_html: Optional[str] = None
    if ui_path.exists():
        _ui_html = ui_path.read_text()

    async def homepage(request):
        if _ui_html:
            return HTMLResponse(_ui_html)
        return HTMLResponse("<h1>Azure Pricing MCP Server</h1><p>MCP endpoint: <code>/mcp</code></p>")

    # Build combined routes:
    # 1. Test UI at /
    # 2. SSE routes (/sse, /messages)
    # 3. Streamable HTTP route (/mcp)
    ui_routes = [Route("/", homepage)]
    combined_routes = ui_routes + list(sse_app.routes) + list(streamable_app.routes)
    app = Starlette(
        routes=combined_routes,
        lifespan=lambda app: mcp.session_manager.run(),
    )

    logger.info("Starting Azure Pricing MCP Server with ALL transports")
    logger.info(f"Listening on {host}:{port}")
    logger.info(f"Test UI:                  http://{host}:{port}/")
    logger.info(f"Streamable HTTP endpoint: http://{host}:{port}/mcp")
    logger.info(f"SSE endpoint:             http://{host}:{port}/sse")

    uvicorn.run(app, host=host, port=port)


def main():
    """Main entry point for the server."""
    args = parse_args()

    # Update host/port from CLI args
    mcp.settings.host = args.host
    mcp.settings.port = args.port

    if args.transport == "all":
        _run_all_transports(args.host, args.port)
    else:
        logger.info(f"Starting Azure Pricing MCP Server with {args.transport} transport")
        if args.transport in ("sse", "streamable-http"):
            logger.info(f"Listening on {args.host}:{args.port}")
            if args.transport == "streamable-http":
                logger.info(f"Streamable HTTP endpoint: http://{args.host}:{args.port}/mcp")
            elif args.transport == "sse":
                logger.info(f"SSE endpoint: http://{args.host}:{args.port}/sse")

        mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()