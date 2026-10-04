"""EvidenceGraph-X backend package."""
import sys

if sys.platform == 'win32':
    import truststore
    truststore.inject_into_ssl()
