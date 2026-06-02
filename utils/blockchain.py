import json
import base64
import time
import threading
from web3 import Web3
from django.conf import settings

POLYGON_RPC = "https://polygon-amoy.g.alchemy.com/v2/6ua2Hv6WiSZEaByN7SuxD"

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
            {"indexed": True,  "internalType": "address", "name": "from",    "type": "address"},
            {"indexed": True,  "internalType": "address", "name": "to",      "type": "address"},
            {"indexed": True,  "internalType": "uint256", "name": "tokenId", "type": "uint256"}
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
    nft_image = (
        str(ticket.qr_image)
        if ticket.qr_image and str(ticket.qr_image).startswith('http')
        else "https://res.cloudinary.com/master-events/image/upload/v1/master_events/nft_ticket_cover.png"
    )
    return {
        "name":         f"Master Events — {ticket.event.name} #{ticket.ticket_id}",
        "description":  (
            f"Official NFT ticket for {ticket.event.name} on {ticket.event.date} "
            f"at {ticket.event.venue}, {getattr(ticket.event, 'city', 'Ghana')}. "
            f"Secured on Polygon blockchain. Cannot be duplicated or forged."
        ),
        "image":        nft_image,
        "external_url": f"https://master-events-bi7m.vercel.app/verify/{ticket.ticket_id}",
        "attributes": [
            {"trait_type": "Event",      "value": ticket.event.name},
            {"trait_type": "Date",       "value": str(ticket.event.date)},
            {"trait_type": "Venue",      "value": ticket.event.venue},
            {"trait_type": "City",       "value": getattr(ticket.event, 'city', 'Ghana')},
            {"trait_type": "Ticket ID",  "value": str(ticket.ticket_id)},
            {"trait_type": "Quantity",   "value": ticket.quantity},
            {"trait_type": "Category",   "value": ticket.event.category},
            {"trait_type": "Price Paid", "value": str(ticket.price_paid)},
            {"trait_type": "Is Resale",  "value": str(ticket.is_resale)},
            {"trait_type": "Platform",   "value": "Master Events Ghana"},
        ]
    }


def build_token_uri(ticket):
    backend_url = getattr(settings, 'BACKEND_URL', '').rstrip('/')
    if backend_url:
        return f"{backend_url}/api/nft/metadata/{ticket.ticket_id}/"
    metadata  = build_ticket_metadata(ticket)
    meta_json = json.dumps(metadata)
    meta_b64  = base64.b64encode(meta_json.encode()).decode()
    return "data:application/json;base64," + meta_b64


def _parse_token_id_from_receipt(receipt, contract):
    """
    Extract token ID from receipt using ABI event parsing only.
    Falls back to None if parsing fails — tx_hash is still valid.
    """
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            events = contract.events.Transfer().process_receipt(receipt)
        if events:
            return int(events[0]['args']['tokenId'])
    except Exception:
        pass
    return None


def mint_ticket_nft(ticket, owner_wallet_address=None, max_retries=3):
    """
    Mint NFT sequentially on Polygon Amoy Testnet.
    Fixed: always fetches fresh nonce, higher gas price multiplier.
    """
    if not is_blockchain_enabled():
        print("Blockchain not configured — skipping NFT mint")
        return None

    for attempt in range(1, max_retries + 1):
        try:
            contract = get_contract()
            if not contract:
                print("Could not get contract")
                return None

            token_uri        = build_token_uri(ticket)
            platform_account = w3.eth.account.from_key(settings.BLOCKCHAIN_PRIVATE_KEY)
            platform_address = platform_account.address
            to_address       = (
                Web3.to_checksum_address(owner_wallet_address)
                if owner_wallet_address
                else platform_address
            )

            print(f"[Attempt {attempt}/{max_retries}] Minting NFT to {to_address}...")

            nonce     = w3.eth.get_transaction_count(platform_address, 'pending')
            gas_price = int(w3.eth.gas_price * 1.5)

            try:
                estimated_gas = contract.functions.mintTicket(
                    to_address, token_uri
                ).estimate_gas({'from': platform_address})
                gas_limit = int(estimated_gas * 1.3)
            except Exception:
                gas_limit = 300000

            txn = contract.functions.mintTicket(
                to_address,
                token_uri
            ).build_transaction({
                'from':     platform_address,
                'nonce':    nonce,
                'gas':      gas_limit,
                'gasPrice': gas_price,
                'chainId':  80002,
            })

            signed_txn = w3.eth.account.sign_transaction(txn, settings.BLOCKCHAIN_PRIVATE_KEY)
            tx_hash    = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
            print(f"TX sent: {tx_hash.hex()}")

            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            if receipt.status == 1:
                token_id    = _parse_token_id_from_receipt(receipt, contract)
                tx_hash_hex = tx_hash.hex()
                print(f"✅ NFT minted! Token ID: {token_id}, TX: {tx_hash_hex}")
                return {
                    'token_id':  token_id,
                    'tx_hash':   tx_hash_hex,
                    'token_uri': token_uri,
                }
            else:
                print(f"❌ Transaction failed on attempt {attempt}.")

        except Exception as e:
            print(f"NFT mint error (attempt {attempt}): {e}")
            if attempt < max_retries:
                time.sleep(3 * attempt)

    print(f"NFT mint failed after {max_retries} attempts for ticket {ticket.ticket_id}")
    return None


def mint_ticket_nft_async(ticket, owner_wallet_address=None, callback=None):
    """
    Mint NFT in background thread — doesn't block API response.
    """
    def _mint():
        result = mint_ticket_nft(ticket, owner_wallet_address)
        if result and callback:
            callback(result)
        elif not result:
            try:
                from tickets.models import Ticket as TicketModel
                t = TicketModel.objects.get(pk=ticket.pk)
                if not t.nft_tx_hash:
                    t.nft_mint_failed = True
                    t.save(update_fields=['nft_mint_failed'])
                    print(f"⚠️ Marked ticket {t.ticket_id} as mint_failed for retry")
            except Exception as e:
                print(f"Could not mark mint_failed: {e}")

    thread = threading.Thread(target=_mint, daemon=True)
    thread.start()
    return thread


def retry_failed_mints():
    """
    Sequential retry — fixes nonce collision from parallel threading.
    Run from shell: from utils.blockchain import retry_failed_mints; retry_failed_mints()
    """
    try:
        from tickets.models import Ticket as TicketModel
        failed = TicketModel.objects.filter(
            nft_tx_hash__isnull=True,
            nft_mint_failed=True,
            status__in=['active', 'resale']
        )
        count = failed.count()
        print(f"Found {count} tickets with failed mints")
        if count == 0:
            return

        for ticket in failed:
            print(f"--- Minting {ticket.ticket_id} ---")
            result = mint_ticket_nft(ticket)
            if result:
                ticket.nft_token_id    = result['token_id']
                ticket.nft_tx_hash     = result['tx_hash']
                ticket.nft_token_uri   = result['token_uri']
                ticket.nft_mint_failed = False
                ticket.save(update_fields=[
                    'nft_token_id', 'nft_tx_hash',
                    'nft_token_uri', 'nft_mint_failed'
                ])
                print(f"✅ {ticket.ticket_id} → Token #{result['token_id']}, TX: {result['tx_hash'][:16]}...")
                try:
                    from utils.emails import notify_nft_minted
                    threading.Thread(
                        target=notify_nft_minted,
                        args=(ticket,),
                        daemon=True
                    ).start()
                except Exception as e:
                    print(f"NFT notify error: {e}")
            else:
                print(f"❌ {ticket.ticket_id} failed — will retry next time")
            time.sleep(2)

        print("--- Retry complete ---")

    except Exception as e:
        print(f"retry_failed_mints error: {e}")


def transfer_ticket_nft(token_id, from_wallet, to_wallet):
    if not is_blockchain_enabled():
        return None
    try:
        contract         = get_contract()
        if not contract:
            return None

        platform_account = w3.eth.account.from_key(settings.BLOCKCHAIN_PRIVATE_KEY)
        platform_address = platform_account.address

        nonce     = w3.eth.get_transaction_count(platform_address, 'pending')
        gas_price = int(w3.eth.gas_price * 1.5)

        try:
            estimated_gas = contract.functions.transferFrom(
                Web3.to_checksum_address(from_wallet),
                Web3.to_checksum_address(to_wallet),
                token_id
            ).estimate_gas({'from': platform_address})
            gas_limit = int(estimated_gas * 1.3)
        except Exception:
            gas_limit = 200000

        txn = contract.functions.transferFrom(
            Web3.to_checksum_address(from_wallet),
            Web3.to_checksum_address(to_wallet),
            token_id
        ).build_transaction({
            'from':     platform_address,
            'nonce':    nonce,
            'gas':      gas_limit,
            'gasPrice': gas_price,
            'chainId':  80002,
        })

        signed_txn = w3.eth.account.sign_transaction(txn, settings.BLOCKCHAIN_PRIVATE_KEY)
        tx_hash    = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
        receipt    = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

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
    return "https://amoy.polygonscan.com/tx/" + tx_hash