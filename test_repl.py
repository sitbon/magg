#!/usr/bin/env python3
"""Test the asyncio REPL implementation."""

import asyncio
from magg.mbro.acon import interact

async def main():
    print("Testing asyncio REPL implementation")
    print("Type 'exit()' to exit the REPL")
    print()
    
    # Test with some predefined locals
    test_var = "Hello from main!"
    
    # Call the interact function
    return_code = await interact(
        banner="Test REPL Session",
        locals={"test_var": test_var, "asyncio": asyncio}
    )
    
    print(f"\nREPL exited with return code: {return_code}")
    return return_code

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    print(f"Script exiting with code: {exit_code}")