# Ebaadurrub Awan, Jawad Syed, Ibrahim Ihsan

import sys
# --- Class: SessionState ---
class SessionState:
    """Tracks current session details and enforces business rules."""
    def __init__(self):
        self.logged_in = False
        self.admin_mode = False
        self.account_holder_name = ""
        self.total_withdrawn = 0.0

    def startSession(self, sessionMode, accountHolderName):
        self.logged_in = True
        self.admin_mode = (sessionMode.lower() == "admin")
        self.account_holder_name = accountHolderName
        self.total_withdrawn = 0.0

    def endSession(self):
        self.__init__()

    def isLoggedIn(self): return self.logged_in
    def isAdminMode(self): return self.admin_mode
    def getCurrentAccountHolderName(self): return self.account_holder_name
    def addToTotalWithdrawn(self, amount): self.total_withdrawn += amount

# --- Class: BankAccountsFile ---
class BankAccountsFile:
    """Loads and validates account information from the Current User Accounts File."""
    def __init__(self):
        self.accounts = {}

    def loadFromFile(self, filePath):
        """Reads 37-character fixed-length records[cite: 29]."""
        try:
            with open(filePath, 'r') as f:
                for line in f:
                    if line.startswith("00000"): break
                    acc_num = line[0:5]
                    name = line[6:26].strip()
                    status = line[27:28]
                    balance = float(line[29:37])
                    self.accounts[acc_num] = {"name": name, "status": status, "balance": balance}
        except FileNotFoundError:
            raise FileNotFoundError(f"ERROR: Accounts file not found at {filePath}")

    def doesAccountExist(self, accNum): return accNum in self.accounts
    def isAccountDisabled(self, accNum): return self.accounts.get(accNum, {}).get("status") == "D"
    def isAccountOwnedBy(self, accNum, name): return self.accounts.get(accNum, {}).get("name") == name

# --- Class: DailyTransactionFileWriter ---
class DailyTransactionFileWriter:
    """Formats and saves 40-character transaction records[cite: 37, 39]."""
    def __init__(self):
        self.records = []

    def formatTransactionRecordLine(self, code, name, accNum, amount, misc="  "):
        # Format: CC AAAAAAAAAAAAAAAAAAAA NNNNN PPPPPPPP MM [cite: 52]
        return f"{code} {name:<20} {accNum:>5} {amount:08.2f} {misc}"

    def addTransactionRecord(self, recordLine):
        self.records.append(recordLine)

    def addEndOfSessionRecord(self):
        self.records.append(self.formatTransactionRecordLine("00", "", "00000", 0.0))

    def writeToFile(self, filePath):
        with open(filePath, 'w') as f:
            for r in self.records: f.write(r + "\n")

# --- Class: FrontEndController ---
class FrontEndController:
    """The 'brain' that processes input and enforces session rules[cite: 17, 18]."""
    def __init__(self, session, accounts, writer):
        self.session = session
        self.accounts = accounts
        self.writer = writer

    def handleInputLine(self, inputLine):
        code = self.extractTransactionCode(inputLine)
        if code == "login": return self.handleLogin()
        if code == "logout": return self.handleLogout()
        return self.handleNonLoginTransaction(code)

    def extractTransactionCode(self, inputLine):
        return inputLine.strip().lower()

    def handleLogin(self):
        if self.session.isLoggedIn(): return "ERROR: Already logged in."
        mode = input("Session type (admin/standard): ").strip().lower()
        name = "" if mode == "admin" else input("Account holder name: ").strip()
        
        try:
            self.accounts.loadFromFile("accounts.txt")
            self.session.startSession(mode, name)
            return "Login successful.\nOptions: withdrawal, logout (Admin can also: create, delete, disable)"
        except FileNotFoundError as e:
            return str(e)

    def handleNonLoginTransaction(self, code):
        if not self.session.isLoggedIn(): return "ERROR: Must login first[cite: 14]."

        if code == "withdrawal":
            acc_num = input("Enter account number (code): ").strip() # Asks for code
            if not self.accounts.doesAccountExist(acc_num): return "ERROR: Account does not exist."
            if self.accounts.isAccountDisabled(acc_num): return "ERROR: Account is disabled[cite: 22]."
            
            try:
                amount = float(input("Enter amount of money: ")) # Asks for amount
                if amount <= 0: return "ERROR: Amount must be positive."
                
                # Enforce $500 limit for Standard
                if not self.session.isAdminMode() and amount > 500.00:
                    return "ERROR: Withdrawal limit exceeded ($500.00)."

                record = self.writer.formatTransactionRecordLine("01", self.session.getCurrentAccountHolderName(), acc_num, amount)
                self.writer.addTransactionRecord(record)
                return "Withdrawal successful."
            except ValueError:
                return "ERROR: Non-numeric amount input."

        return "ERROR: Unknown transaction code."

    def handleLogout(self):
        if not self.session.isLoggedIn(): return "ERROR: Not logged in[cite: 14]."
        self.writer.addEndOfSessionRecord()
        self.writer.writeToFile("transactions.txt")
        self.session.endSession()
        return "Logout successful. Transaction file written."

# --- Class: FrontEndApplication ---
class FrontEndApplication:
    """Initializes and runs the program reading from stdin[cite: 11, 12]."""
    def __init__(self):
        self.session = SessionState()
        self.accounts = BankAccountsFile()
        self.writer = DailyTransactionFileWriter()
        self.controller = FrontEndController(self.session, self.accounts, self.writer)

    def run(self):
        print("Banking System CLI Started.")
        while True:
            try:
                line = sys.stdin.readline().strip()
                if not line: break
                print(self.controller.handleInputLine(line))
            except EOFError: break

if __name__ == "__main__":
    app = FrontEndApplication()
    app.run()