#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FlowCore Model Manager v1.0
Mission 5: Intelligent Model Download System

Features:
- Download models from HuggingFace
- Validate SHA256 hash
- Update management
- Remove models
- Version switching
- Intelligent cache
- Rollback support
"""

import os
import json
import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class ModelInfo:
    """Information about a downloaded model."""
    name: str
    path: str
    size_mb: float
    quantization: str
    sha256_hash: str
    download_date: str
    last_used: str
    use_count: int = 0
    version: str = "1.0"


class ModelManager:
    """Intelligent model download and management system."""
    
    def __init__(self, base_dir: str = "/workspace/FlowCore/Models"):
        self.base_dir = Path(base_dir)
        self.cache_dir = self.base_dir / ".cache"
        self.metadata_file = self.base_dir / "models.json"
        self.models: Dict[str, ModelInfo] = {}
        
        # Create directories
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Load existing metadata
        self._load_metadata()
    
    def _load_metadata(self):
        """Load model metadata from disk."""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, "r") as f:
                    data = json.load(f)
                    for name, info in data.items():
                        self.models[name] = ModelInfo(**info)
            except Exception as e:
                print(f"Warning: Could not load metadata: {e}")
    
    def _save_metadata(self):
        """Save model metadata to disk."""
        data = {name: {
            "name": info.name,
            "path": info.path,
            "size_mb": info.size_mb,
            "quantization": info.quantization,
            "sha256_hash": info.sha256_hash,
            "download_date": info.download_date,
            "last_used": info.last_used,
            "use_count": info.use_count,
            "version": info.version
        } for name, info in self.models.items()}
        
        with open(self.metadata_file, "w") as f:
            json.dump(data, f, indent=2)
    
    def calculate_sha256(self, filepath: str) -> str:
        """Calculate SHA256 hash of a file."""
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    
    def download_model(self, url: str, model_name: str, expected_hash: Optional[str] = None) -> bool:
        """
        Download a model from URL with validation.
        
        Args:
            url: HuggingFace or direct download URL
            model_name: Name to save the model as
            expected_hash: Optional expected SHA256 hash for validation
        
        Returns:
            True if download successful and validated
        """
        print(f"\n[DOWNLOAD] Starting download: {model_name}")
        print(f"[DOWNLOAD] URL: {url}")
        
        # Create temp directory for download
        temp_dir = self.cache_dir / "downloads"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        temp_file = temp_dir / f"{model_name}.gguf.tmp"
        final_path = self.base_dir / f"{model_name}.gguf"
        
        try:
            # Use wget or curl for download with progress
            if shutil.which("wget"):
                cmd = ["wget", "-O", str(temp_file), "--show-progress", url]
            elif shutil.which("curl"):
                cmd = ["curl", "-L", "-o", str(temp_file), url]
            else:
                print("[ERROR] Neither wget nor curl found")
                return False
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"[ERROR] Download failed: {result.stderr}")
                return False
            
            # Calculate hash
            print("\n[VALIDATE] Calculating SHA256 hash...")
            actual_hash = self.calculate_sha256(str(temp_file))
            print(f"[VALIDATE] Hash: {actual_hash}")
            
            # Validate hash if provided
            if expected_hash:
                if actual_hash.lower() != expected_hash.lower():
                    print(f"[ERROR] Hash mismatch!")
                    print(f"[ERROR] Expected: {expected_hash}")
                    print(f"[ERROR] Got:      {actual_hash}")
                    temp_file.unlink()
                    return False
                print("[VALIDATE] Hash verified ✓")
            
            # Move to final location
            shutil.move(str(temp_file), str(final_path))
            
            # Get file size
            size_mb = final_path.stat().st_size / (1024 * 1024)
            
            # Create model info
            now = datetime.now().isoformat()
            model_info = ModelInfo(
                name=model_name,
                path=str(final_path),
                size_mb=round(size_mb, 2),
                quantization="auto",  # Will be detected
                sha256_hash=actual_hash,
                download_date=now,
                last_used=now,
                use_count=0
            )
            
            self.models[model_name] = model_info
            self._save_metadata()
            
            print(f"\n[SUCCESS] Model downloaded: {model_name}")
            print(f"[SUCCESS] Size: {size_mb:.2f} MB")
            print(f"[SUCCESS] Location: {final_path}")
            
            return True
            
        except Exception as e:
            print(f"[ERROR] Download failed: {e}")
            # Cleanup on failure
            if temp_file.exists():
                temp_file.unlink()
            return False
    
    def remove_model(self, model_name: str, confirm: bool = True) -> bool:
        """Remove a model from the system."""
        if model_name not in self.models:
            print(f"[ERROR] Model '{model_name}' not found")
            return False
        
        model_info = self.models[model_name]
        model_path = Path(model_info.path)
        
        if confirm:
            response = input(f"Remove '{model_name}' ({model_info.size_mb:.2f} MB)? [y/N]: ")
            if response.lower() != 'y':
                print("[CANCEL] Removal cancelled")
                return False
        
        try:
            # Backup before removal (for rollback)
            backup_dir = self.cache_dir / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / f"{model_name}.backup"
            
            if model_path.exists():
                shutil.copy2(str(model_path), str(backup_path))
                print(f"[BACKUP] Created backup at {backup_path}")
            
            # Remove model file
            model_path.unlink()
            
            # Remove from metadata
            del self.models[model_name]
            self._save_metadata()
            
            print(f"[SUCCESS] Model '{model_name}' removed")
            return True
            
        except Exception as e:
            print(f"[ERROR] Removal failed: {e}")
            return False
    
    def rollback_model(self, model_name: str) -> bool:
        """Restore a model from backup."""
        backup_path = self.cache_dir / "backups" / f"{model_name}.backup"
        
        if not backup_path.exists():
            print(f"[ERROR] No backup found for '{model_name}'")
            return False
        
        final_path = self.base_dir / f"{model_name}.gguf"
        
        try:
            shutil.copy2(str(backup_path), str(final_path))
            
            # Restore metadata if available
            # (In production, would also restore metadata backup)
            
            print(f"[SUCCESS] Model '{model_name}' restored from backup")
            return True
            
        except Exception as e:
            print(f"[ERROR] Rollback failed: {e}")
            return False
    
    def switch_version(self, model_name: str, new_url: str, new_hash: str) -> bool:
        """Switch to a different version of a model."""
        print(f"[SWITCH] Switching version for '{model_name}'")
        
        # Backup current version
        if model_name in self.models:
            self.remove_model(model_name, confirm=False)
        
        # Download new version
        success = self.download_model(new_url, model_name, new_hash)
        
        if success:
            self.models[model_name].version = "2.0"  # Increment version
            self._save_metadata()
            print(f"[SUCCESS] Switched to new version")
        
        return success
    
    def list_models(self) -> List[Dict[str, Any]]:
        """List all downloaded models."""
        models_list = []
        for name, info in self.models.items():
            models_list.append({
                "name": info.name,
                "size_mb": info.size_mb,
                "quantization": info.quantization,
                "download_date": info.download_date,
                "last_used": info.last_used,
                "use_count": info.use_count,
                "path": info.path
            })
        return models_list
    
    def get_model(self, model_name: str) -> Optional[ModelInfo]:
        """Get information about a specific model."""
        if model_name in self.models:
            # Update last used
            self.models[model_name].last_used = datetime.now().isoformat()
            self.models[model_name].use_count += 1
            self._save_metadata()
            return self.models[model_name]
        return None
    
    def clear_cache(self, keep_recent: int = 3) -> int:
        """Clear old models from cache, keeping most recently used."""
        if len(self.models) <= keep_recent:
            print(f"[INFO] Only {len(self.models)} models, nothing to clear")
            return 0
        
        # Sort by last used
        sorted_models = sorted(
            self.models.items(),
            key=lambda x: x[1].last_used,
            reverse=True
        )
        
        removed_count = 0
        for name, info in sorted_models[keep_recent:]:
            if self.remove_model(name, confirm=False):
                removed_count += 1
        
        # Clear download cache
        download_cache = self.cache_dir / "downloads"
        if download_cache.exists():
            shutil.rmtree(download_cache)
        
        print(f"[CLEANUP] Removed {removed_count} old models")
        return removed_count
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_size = sum(info.size_mb for info in self.models.values())
        
        return {
            "total_models": len(self.models),
            "total_size_mb": round(total_size, 2),
            "cache_dir": str(self.cache_dir),
            "models_dir": str(self.base_dir)
        }
    
    def print_status(self):
        """Print human-readable status."""
        print("=" * 60)
        print("FLOWCORE MODEL MANAGER STATUS")
        print("=" * 60)
        
        stats = self.get_cache_stats()
        print(f"\nTotal Models: {stats['total_models']}")
        print(f"Total Size: {stats['total_size_mb']:.2f} MB")
        print(f"Models Directory: {stats['models_dir']}")
        
        if self.models:
            print("\n" + "-" * 60)
            print("Downloaded Models:")
            print("-" * 60)
            print(f"{'Name':<30} {'Size':<12} {'Last Used':<20}")
            print("-" * 60)
            
            for name, info in self.models.items():
                print(f"{name:<30} {info.size_mb:<12.2f}MB {info.last_used[:19]}")
        
        print("=" * 60)


if __name__ == "__main__":
    manager = ModelManager()
    manager.print_status()
    
    # Example usage:
    # manager.download_model(
    #     url="https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/q4_k_m.gguf",
    #     model_name="qwen2.5-3b-instruct-q4",
    #     expected_hash="abc123..."
    # )
    # 
    # models = manager.list_models()
    # for m in models:
    #     print(m)
