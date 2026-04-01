import json
import os
import threading
from web3 import Web3
from django.conf import settings

POLYGON_RPC = "https://polygon-mainnet.g.alchemy.com/v2/6ua2Hv6WiSZEaByN7SuxD"

try:
    w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
    print(f"Blockchain connected: {w3.is_connected()}")
except Exception as e:
    print(f"Blockchain connection error: {e}")
    w3 = None

NFT_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "string", "name": "uri", "type": "string"}
        ],
        "name": "mintTicket",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "tokenId", "type": "uint256"}
        ],
        "name": "ownerOf",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "from", "type": "address"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "tokenId", "type": "uint256"}
        ],
        "name": "transferFrom",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "tokenId", "type": "uint256"}
        ],
        "name": "tokenURI",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "from", "type": "address"},
            {"indexed": True, "internalType": "address", "name": "to", "type": "address"},
            {"indexed": True, "internalType": "uint256", "name": "tokenId", "type": "uint256"}
        ],
        "name": "Transfer",
        "type": "event"
    }
]


def get_contract():
    contract_address = getattr(settings, 'NFT_CONTRACT_ADDRESS', '')
    if not contract_address or not w3:
        return None
    try:
        return w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=NFT_ABI
        )
    except Exception as e:
        print(f"Contract error: {e}")
        return None


def is_blockchain_enabled():
    return (
        bool(getattr(settings, 'NFT_CONTRACT_ADDRESS', '')) and
        bool(getattr(settings, 'BLOCKCHAIN_PRIVATE_KEY', '')) and
        w3 is not None and
        w3.is_connected()
    )


def build_ticket_metadata(ticket):
    return {
        "name": f"Master Events Ticket #{ticket.ticket_id}",
        "description": f"Official NFT ticket for {ticket.event.name} on {ticket.event.date} at {ticket.event.venue}. Secured on Polygon blockchain.",
        "image": "https://master-events-bi7m.vercel.app/ticket-nft.png",
        "external_url": f"https://master-events-bi7m.vercel.app",
        "attributes": [
            {"trait_type": "Event", "value": ticket.event.name},
            {"trait_type": "Date", "value": str(ticket.event.date)},
            {"trait_type": "Venue", "value": ticket.event.venue},
            {"trait_type": "City", "value": ticket.event.city},
            {"trait_type": "Ticket ID", "value": str(ticket.ticket_id)},
            {"trait_type": "Quantity", "value": ticket.quantity},
            {"trait_type": "Category", "value": ticket.event.category},
            {"trait_type": "Price Paid", "value": str(ticket.price_paid)},
        ]
    }


def upload_metadata_to_ipfs(metadata):
    import requests
    try:
        thirdweb_secret = getattr(settings, 'THIRDWEB_SECRET_KEY', '')
        if not thirdweb_secret:
            # Use inline JSON as fallback
            return None

        response = requests.post(
            "https://storage.thirdweb.com/ipfs/upload",
            json=metadata,
            headers={
                "Authorization": f"Bearer {thirdweb_secret}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        if response.status_code == 200:
            data = response.json()
            ipfs_hash = data.get('IpfsHash', '')
            print(f"IPFS uploaded: {ipfs_hash}")
            return ipfs_hash
        return None
    except Exception as e:
        print(f"IPFS upload error: {e}")
        return None


def mint_ticket_nft(ticket, owner_wallet_address=None):
    """Mint NFT synchronously and return result"""
    if not is_blockchain_enabled():
        print("Blockchain not configured or not connected — skipping NFT mint")
        return None

    try:
        contract = get_contract()
        if not contract:
            print("Could not get contract")
            return None

        # Build metadata
        metadata = build_ticket_metadata(ticket)

        # Try IPFS, fallback to data URI
        ipfs_hash = upload_metadata_to_ipfs(metadata)
        if ipfs_hash:
            token_uri = f"ipfs://{ipfs_hash}"
        else:
            import json as json_mod
            import base64 as base64_mod
            meta_json = json_mod.dumps(metadata)
            meta_b64 = base64_mod.b64encode(meta_json.encode()).decode()
            token_uri = f"data:application/json;base64,{meta_b64}"

        platform_account = w3.eth.account.from_key(settings.BLOCKCHAIN_PRIVATE_KEY)
        platform_address = platform_account.address

        # Use platform address if no owner wallet
        to_address = owner_wallet_address if owner_wallet_address else platform_address

        print(f"Minting NFT to {to_address}...")

        nonce = w3.eth.get_transaction_count(platform_address)
        gas_price = w3.eth.gas_price

        # Add 20% gas buffer
        gas_price_with_buffer = int(gas_price * 1.2)

        txn = contract.functions.mintTicket(
            Web3.to_checksum_address(to_address),
            token_uri
        ).build_transaction({
            'from': platform_address,
            'nonce': nonce,
            'gas': 300000,
            'gasPrice': gas_price_with_buffer,
            'chainId': 137,  # Polygon mainnet
        })

        signed_txn = w3.eth.account.sign_transaction(txn, settings.BLOCKCHAIN_PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)

        print(f"TX sent: {tx_hash.hex()}")

        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        if receipt.status == 1:
            transfer_events = contract.events.Transfer().process_receipt(receipt)
            if transfer_events:
                token_id = transfer_events[0]['args']['tokenId']
                tx_hash_hex = tx_hash.hex()
                print(f"✅ NFT minted! Token ID: {token_id}, TX: {tx_hash_hex}")
                return {
                    'token_id': token_id,
                    'tx_hash': tx_hash_hex,
                    'token_uri': token_uri,
                }
        else:
            print(f"❌ Transaction failed! Receipt: {receipt}")
        return None

    except Exception as e:
        print(f"❌ NFT mint error: {e}")
        return None


def mint_ticket_nft_async(ticket, owner_wallet_address=None, callback=None):
    """Mint NFT in background thread — doesn't block the API response"""
    def _mint():
        result = mint_ticket_nft(ticket, owner_wallet_address)
        if result and callback:
            callback(result)
    thread = threading.Thread(target=_mint, daemon=True)
    thread.start()
    return thread


def transfer_ticket_nft(token_id, from_wallet, to_wallet):
    if not is_blockchain_enabled():
        return None

    try:
        contract = get_contract()
        if not contract:
            return None

        platform_account = w3.eth.account.from_key(settings.BLOCKCHAIN_PRIVATE_KEY)
        platform_address = platform_account.address

        nonce = w3.eth.get_transaction_count(platform_address)
        gas_price = w3.eth.gas_price

        txn = contract.functions.transferFrom(
            Web3.to_checksum_address(from_wallet),
            Web3.to_checksum_address(to_wallet),
            token_id
        ).build_transaction({
            'from': platform_address,
            'nonce': nonce,
            'gas': 200000,
            'gasPrice': int(gas_price * 1.2),
            'chainId': 137,
        })

        signed_txn = w3.eth.account.sign_transaction(txn, settings.BLOCKCHAIN_PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        if receipt.status == 1:
            tx_hash_hex = tx_hash.hex()
            print(f"✅ NFT transferred! TX: {tx_hash_hex}")
            return tx_hash_hex
        return None

    except Exception as e:
        print(f"NFT transfer error: {e}")
        return None


def verify_ticket_ownership(token_id, wallet_address):
    if not is_blockchain_enabled():
        return True
    try:
        contract = get_contract()
        if not contract:
            return True
        owner = contract.functions.ownerOf(token_id).call()
        return owner.lower() == wallet_address.lower()
    except Exception as e:
        print(f"NFT ownership check error: {e}")
        return False


def get_polygon_explorer_url(tx_hash):
    if not tx_hash:
        return None
    return f"https://polygonscan.com/tx/{tx_hash}"