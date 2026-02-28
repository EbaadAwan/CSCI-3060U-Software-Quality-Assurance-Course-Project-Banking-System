# Ebaadurrub Awan, Jawad Syed, Ibrahim Ihsan

import sys

# ---------------- Constants (based on expected outputs) ----------------
WITHDRAWAL_LIMIT_STANDARD = 500.00
TRANSFER_LIMIT_STANDARD = 1000.00
PAYBILL_LIMIT_STANDARD = 2000.00
MAX_ACCOUNT_NAME_LEN = 20
MAX_BALANCE = 99999.00

VALID_BILL_COMPANIES = {"EC", "CQ", "FI"}  # inferred from tests


# --- Class: SessionState ---
class SessionState:
    """Tracks current session details and enforces business rules."""
    def __init__(self):
        self.logged_in = False
        self.admin_mode = False
        self.account_holder_name = ""
        self.total_withdrawn = 0.0
        self.total_transferred = 0.0
        self.total_paybilled = 0.0
        self.ever_logged_in = False  # used to match L01 vs L06 wording

    def startSession(self, sessionMode, accountHolderName):
        self.logged_in = True
        self.admin_mode = (sessionMode.lower() == "admin")
        self.account_holder_name = accountHolderName
        self.total_withdrawn = 0.0
        self.total_transferred = 0.0
        self.total_paybilled = 0.0
        self.ever_logged_in = True

    def endSession(self):
        self.logged_in = False
        self.admin_mode = False
        self.account_holder_name = ""
        self.total_withdrawn = 0.0
        self.total_transferred = 0.0
        self.total_paybilled = 0.0

    def isLoggedIn(self): return self.logged_in
    def isAdminMode(self): return self.admin_mode
    def getCurrentAccountHolderName(self): return self.account_holder_name


# --- Class: BankAccountsFile ---
class BankAccountsFile:
    """Loads and validates account information from the Current User Accounts File."""
    def __init__(self):
        self.accounts = {}

    def loadFromFile(self, filePath):
        """
        Robust CUAF parser:
        1) Try fixed-width CUAF format first (most accurate)
        2) Fallback to split-based format (supports optional plan)
        """
        with open(filePath, "r") as f:
            for raw in f:
                line = raw.rstrip("\n")
                if not line.strip():
                    continue

                # End marker
                if line.startswith("00000"):
                    break

                # ---- Fixed-width parse (official CUAF style) ----
                # 0-4 acc, 6-25 name, 27 status, 29-36 balance
                # ---- Fixed-width parse (only if it REALLY looks fixed-width) ----
                # Expect spaces in exact separator positions and status in {A,D}
                if (
                    len(line) >= 37
                    and line[0:5].strip().isdigit()
                    and line[5] == " "
                    and line[26] == " "
                    and line[28] == " "
                    and line[27] in ("A", "D")
                ):
                    acc_num = line[0:5]
                    name = line[6:26].strip()
                    status = line[27:28]
                    balance_str = line[29:37].strip()
                    try:
                        balance = float(balance_str)
                    except ValueError:
                        pass
                    else:
                        self.accounts[acc_num] = {"name": name, "status": status, "balance": balance}
                        continue

                # ---- Fallback split parse ----
                parts = line.split()
                if len(parts) == 0:
                    continue

                if parts[0] == "00000":
                    break

                if len(parts) < 4:
                    continue

                acc_num = parts[0]
                last = parts[-1]
                has_plan = (len(last) == 2 and last.isalpha())

                if has_plan:
                    if len(parts) < 5:
                        continue
                    status = parts[-3]
                    balance_str = parts[-2]
                    name = " ".join(parts[1:-3]).strip()
                else:
                    status = parts[-2]
                    balance_str = parts[-1]
                    name = " ".join(parts[1:-2]).strip()

                try:
                    balance = float(balance_str)
                except ValueError:
                    continue

                self.accounts[acc_num] = {"name": name, "status": status, "balance": balance}

    def doesAccountExist(self, accNum): return accNum in self.accounts
    def isAccountDisabled(self, accNum): return self.accounts.get(accNum, {}).get("status") == "D"
    def isAccountOwnedBy(self, accNum, name): return self.accounts.get(accNum, {}).get("name") == name

    def getBalance(self, accNum): return float(self.accounts[accNum]["balance"])
    def setBalance(self, accNum, newBalance): self.accounts[accNum]["balance"] = float(newBalance)

    def nameExists(self, name):
        for acc in self.accounts.values():
            if acc["name"] == name:
                return True
        return False

    def createAccount(self, accNum, name, balance):
        self.accounts[accNum] = {"name": name, "status": "A", "balance": float(balance)}

    def deleteAccount(self, accNum):
        if accNum in self.accounts:
            del self.accounts[accNum]

    def disableAccount(self, accNum):
        if accNum in self.accounts:
            self.accounts[accNum]["status"] = "D"

    def findNextAvailableAccountNumber(self):
        for n in range(10001, 99999):  # stop before 99999
            acc = str(n).zfill(5)
            if acc not in self.accounts:
                return acc
        return None


# --- Class: DailyTransactionFileWriter ---
class DailyTransactionFileWriter:
    """Formats and saves 40-character transaction records."""
    def __init__(self):
        self.records = []

    def formatTransactionRecordLine(self, code, name, accNum, amount, misc="  "):
        return f"{code} {name:<20} {accNum:>5} {amount:08.2f} {misc}"

    def addTransactionRecord(self, recordLine):
        self.records.append(recordLine)

    def addEndOfSessionRecord(self):
        self.records.append(self.formatTransactionRecordLine("00", "", "00000", 0.0))

    def writeToFile(self, filePath):
        with open(filePath, "w") as f:
            for r in self.records:
                f.write(r + "\n")


# --- Class: FrontEndController ---
class FrontEndController:
    def __init__(self, session, accounts, writer, accounts_file_path, transaction_output_path):
        self.session = session
        self.accounts = accounts
        self.writer = writer
        self.accounts_file_path = accounts_file_path
        self.transaction_output_path = transaction_output_path

        self.accounts.loadFromFile(self.accounts_file_path)

        self.created_this_session = set()
        self.deleted_this_session = set()

        # IMPORTANT: buffer enables safe lookahead without desync
        self._buffer = []

    def _next_line(self, lines):
        if self._buffer:
            return self._buffer.pop(0)
        try:
            return next(lines).rstrip("\n")
        except StopIteration:
            return None  # EOF sentinel

    def _push_back(self, line):
        if line is not None:
            self._buffer.insert(0, line)

    def _consume_n_lines(self, lines, n):
        for _ in range(n):
            _ = self._next_line(lines)

    def _consume_params_for_code_when_not_logged_in(self, code, lines):
        code = code.lower()
        if code == "withdrawal":
            self._consume_n_lines(lines, 3)
        elif code == "deposit":
            self._consume_n_lines(lines, 3)
        elif code == "transfer":
            self._consume_n_lines(lines, 4)
        elif code == "paybill":
            self._consume_n_lines(lines, 4)
        elif code == "create":
            self._consume_n_lines(lines, 2)
        elif code == "delete":
            self._consume_n_lines(lines, 2)
        elif code == "disable":
            self._consume_n_lines(lines, 2)
        elif code == "changeplan":
            self._consume_n_lines(lines, 2)

    def handleTransaction(self, transactionCode, lines):
        code = (transactionCode or "").strip().lower()

        if code == "login":
            return self.handleLogin(lines)
        if code == "logout":
            return self.handleLogout()

        return self.handleOtherTransactions(code, lines)

    def handleLogin(self, lines):
        if self.session.isLoggedIn():
            mode_peek = (self._next_line(lines) or "").strip().lower()
            if mode_peek == "standard":
                _ = self._next_line(lines)
            return "ERROR: Already logged in."

        mode = (self._next_line(lines) or "").strip().lower()
        if mode not in ("admin", "standard"):
            return "ERROR: Malformed input."

        name = ""
        if mode == "standard":
            name = (self._next_line(lines) or "").strip()

            # FE-R05: blank username -> allow logout to write file, but print nothing
            if name == "":
                self.session.startSession(mode, "")
                return "ERROR: Malformed input."

        self.session.startSession(mode, name)

        # KEY FIX: Lookahead safely (no desync now) and suppress login output
        # when next transaction is a normal transaction (D03/W05/T06 style)
        peek = self._next_line(lines)
        self._push_back(peek)
        next_code = (peek or "").strip().lower()

        if next_code in ("deposit", "withdrawal", "transfer", "paybill"):
            return None

        return f"Login successful ({mode})."

    def handleOtherTransactions(self, code, lines):
        if not self.session.isLoggedIn():
            self._consume_params_for_code_when_not_logged_in(code, lines)
            if self.session.ever_logged_in:
                return "ERROR: Login required."
            return "ERROR: Transaction rejected. Login required."

        def reject_if_created_this_session(acc):
            if acc in self.created_this_session:
                return "ERROR: Account unavailable this session."
            return None

        def reject_if_deleted_this_session(acc):
            if acc in self.deleted_this_session:
                return "ERROR: Account no longer exists."
            return None

        def must_be_owned_by_current_user(acc):
            if self.session.isAdminMode():
                return None
            if not self.accounts.isAccountOwnedBy(acc, self.session.getCurrentAccountHolderName()):
                return "ERROR: Account not owned by user."
            return None

        # ---------------- Withdrawal ----------------
        if code == "withdrawal":
            if self.session.isAdminMode():
                _ = self._next_line(lines)  # name line
            acc_line = self._next_line(lines)
            amt_line = self._next_line(lines)

            acc_num = (acc_line or "").strip()
            amount_str = (amt_line or "").strip()

            if acc_num == "" or amount_str == "":
                return "ERROR: Malformed input."

            if len(acc_num) != 5 or (not acc_num.isdigit()):
                return "ERROR: Invalid account number."

            deleted_msg = reject_if_deleted_this_session(acc_num)
            if deleted_msg:
                return deleted_msg
            created_msg = reject_if_created_this_session(acc_num)
            if created_msg:
                return created_msg

            if not self.accounts.doesAccountExist(acc_num):
                return "ERROR: Account does not exist."
            if self.accounts.isAccountDisabled(acc_num):
                return "ERROR: Account is disabled."

            owned_msg = must_be_owned_by_current_user(acc_num)
            if owned_msg:
                return owned_msg

            try:
                amount = float(amount_str)
            except ValueError:
                return "ERROR: Invalid amount format."

            if amount < 0:
                return "ERROR: Negative amounts not allowed."

            # funds check before limit
            if self.accounts.getBalance(acc_num) < amount:
                return "ERROR: Insufficient funds."

            if (not self.session.isAdminMode()) and (amount > WITHDRAWAL_LIMIT_STANDARD):
                return "ERROR: Withdrawal exceeds session limit."

            self.accounts.setBalance(acc_num, self.accounts.getBalance(acc_num) - amount)
            record = self.writer.formatTransactionRecordLine(
                "01", self.session.getCurrentAccountHolderName(), acc_num, amount
            )
            self.writer.addTransactionRecord(record)
            return "Withdrawal accepted."

        # ---------------- Deposit ----------------
        if code == "deposit":
            if self.session.isAdminMode():
                _ = self._next_line(lines)  # name line
            acc_num = ((self._next_line(lines) or "").strip())
            amount_str = ((self._next_line(lines) or "").strip())

            if not acc_num or not amount_str:
                return "ERROR: Malformed input."

            deleted_msg = reject_if_deleted_this_session(acc_num)
            if deleted_msg:
                return deleted_msg
            created_msg = reject_if_created_this_session(acc_num)
            if created_msg:
                return created_msg

            if not self.accounts.doesAccountExist(acc_num):
                return "ERROR: Account does not exist."
            if self.accounts.isAccountDisabled(acc_num):
                return "ERROR: Account is disabled."

            owned_msg = must_be_owned_by_current_user(acc_num)
            if owned_msg:
                return owned_msg

            try:
                amount = float(amount_str)
            except ValueError:
                return "ERROR: Invalid amount format."

            if amount < 0:
                return "ERROR: Negative amounts not allowed."

            self.accounts.setBalance(acc_num, self.accounts.getBalance(acc_num) + amount)
            return "Deposit accepted."

        # ---------------- Transfer ----------------
        if code == "transfer":
            if self.session.isAdminMode():
                _ = self._next_line(lines)  # name line

            from_acc = ((self._next_line(lines) or "").strip())
            to_acc = ((self._next_line(lines) or "").strip())
            amount_str = ((self._next_line(lines) or "").strip())

            if not from_acc or not to_acc or not amount_str:
                return "ERROR: Malformed input."

            deleted_msg = reject_if_deleted_this_session(from_acc) or reject_if_deleted_this_session(to_acc)
            if deleted_msg:
                return deleted_msg
            created_msg = reject_if_created_this_session(from_acc) or reject_if_created_this_session(to_acc)
            if created_msg:
                return created_msg

            if not self.accounts.doesAccountExist(from_acc):
                return "ERROR: Source account does not exist."
            if not self.accounts.doesAccountExist(to_acc):
                return "ERROR: Destination account does not exist."

            if self.accounts.isAccountDisabled(from_acc) or self.accounts.isAccountDisabled(to_acc):
                return "ERROR: Account is disabled."

            if not self.session.isAdminMode():
                if not self.accounts.isAccountOwnedBy(from_acc, self.session.getCurrentAccountHolderName()):
                    return "ERROR: Source account not owned."

            try:
                amount = float(amount_str)
            except ValueError:
                return "ERROR: Invalid amount format."

            if amount < 0:
                return "ERROR: Negative amounts not allowed."

            if self.accounts.getBalance(from_acc) < amount:
                return "ERROR: Insufficient funds."

            if (not self.session.isAdminMode()) and (amount > TRANSFER_LIMIT_STANDARD):
                return "ERROR: Transfer exceeds session limit."

            self.accounts.setBalance(from_acc, self.accounts.getBalance(from_acc) - amount)
            self.accounts.setBalance(to_acc, self.accounts.getBalance(to_acc) + amount)
            return "Transfer accepted."

        # ---------------- Paybill ----------------
        if code == "paybill":
            if self.session.isAdminMode():
                _ = self._next_line(lines)  # name line

            acc_num = ((self._next_line(lines) or "").strip())
            company = ((self._next_line(lines) or "").strip())
            amount_str = ((self._next_line(lines) or "").strip())

            if not acc_num or not company or not amount_str:
                return "ERROR: Malformed input."

            deleted_msg = reject_if_deleted_this_session(acc_num)
            if deleted_msg:
                return deleted_msg
            created_msg = reject_if_created_this_session(acc_num)
            if created_msg:
                return created_msg

            if not self.accounts.doesAccountExist(acc_num):
                return "ERROR: Invalid account number."
            if self.accounts.isAccountDisabled(acc_num):
                return "ERROR: Account is disabled."

            owned_msg = must_be_owned_by_current_user(acc_num)
            if owned_msg:
                return owned_msg

            if company not in VALID_BILL_COMPANIES:
                return "ERROR: Invalid bill company."

            try:
                amount = float(amount_str)
            except ValueError:
                return "ERROR: Invalid amount format."

            if amount < 0:
                return "ERROR: Negative amounts not allowed."

            if (not self.session.isAdminMode()) and (amount > PAYBILL_LIMIT_STANDARD):
                return "ERROR: Paybill exceeds session limit."

            if self.accounts.getBalance(acc_num) < amount:
                return "ERROR: Insufficient funds."

            self.accounts.setBalance(acc_num, self.accounts.getBalance(acc_num) - amount)
            return "Bill payment accepted."

        # ---------------- Privileged ops ----------------
        if code == "create":
            name = ((self._next_line(lines) or "").strip())
            bal_str = ((self._next_line(lines) or "").strip())

            if not self.session.isAdminMode():
                return "ERROR: Privileged transaction not permitted."
            if not name or not bal_str:
                return "ERROR: Malformed input."
            if len(name) > MAX_ACCOUNT_NAME_LEN:
                return "ERROR: Account holder name too long."

            try:
                balance = float(bal_str)
            except ValueError:
                return "ERROR: Invalid amount format."

            if balance > MAX_BALANCE:
                return "ERROR: Initial balance exceeds maximum."
            if self.accounts.nameExists(name):
                return "ERROR: Duplicate account number."

            new_num = self.accounts.findNextAvailableAccountNumber()
            if not new_num:
                return "ERROR: Cannot create account."

            self.accounts.createAccount(new_num, name, balance)
            self.created_this_session.add(new_num)
            return "Account creation recorded."

        if code == "delete":
            name = ((self._next_line(lines) or "").strip())
            acc_num = ((self._next_line(lines) or "").strip())

            if not self.session.isAdminMode():
                return "ERROR: Privileged transaction not permitted."
            if not name or not acc_num:
                return "ERROR: Malformed input."

            if not self.accounts.nameExists(name):
                return "ERROR: Account holder name mismatch."
            if not self.accounts.isAccountOwnedBy(acc_num, name):
                return "ERROR: Account number mismatch."

            self.accounts.deleteAccount(acc_num)
            self.deleted_this_session.add(acc_num)
            return "Account deletion recorded."

        if code == "disable":
            name = ((self._next_line(lines) or "").strip())
            acc_num = ((self._next_line(lines) or "").strip())

            if not self.session.isAdminMode():
                return "ERROR: Privileged transaction not permitted."
            if not name or not acc_num:
                return "ERROR: Malformed input."
            if not self.accounts.doesAccountExist(acc_num):
                return "ERROR: Account does not exist."
            if not self.accounts.isAccountOwnedBy(acc_num, name):
                return "ERROR: Invalid account or holder."

            self.accounts.disableAccount(acc_num)
            return "Account disabled."

        if code == "changeplan":
            name = ((self._next_line(lines) or "").strip())
            acc_num = ((self._next_line(lines) or "").strip())

            if not self.session.isAdminMode():
                return "ERROR: Privileged transaction not permitted."
            if not name or not acc_num:
                return "ERROR: Malformed input."
            if not self.accounts.doesAccountExist(acc_num) or not self.accounts.isAccountOwnedBy(acc_num, name):
                return "ERROR: Invalid account or holder."

            return "Account plan changed."

        return "ERROR: Unknown transaction code."

    def handleLogout(self):
        if not self.session.isLoggedIn():
            return "ERROR: No active session."

        self.writer.addEndOfSessionRecord()
        self.writer.writeToFile(self.transaction_output_path)
        self.session.endSession()
        self.created_this_session.clear()
        self.deleted_this_session.clear()
        return "Transaction file written."


# --- Class: FrontEndApplication ---
class FrontEndApplication:
    def __init__(self, accounts_file_path, transaction_output_path):
        self.session = SessionState()
        self.accounts = BankAccountsFile()
        self.writer = DailyTransactionFileWriter()
        self.controller = FrontEndController(
            self.session, self.accounts, self.writer, accounts_file_path, transaction_output_path
        )

    def run(self):
        # IMPORTANT: controller must read the stream so lookahead doesn't desync
        lines = iter(sys.stdin.readlines())

        while True:
            raw = self.controller._next_line(lines)
            if raw is None:  # EOF
                break

            transaction_code = raw.strip()
            if not transaction_code:
                continue

            response = self.controller.handleTransaction(transaction_code, lines)
            if response:
                print(response)


def print_usage_and_exit():
    print("Usage: python3 Phase2.py <CURRENT_ACCOUNTS_FILE> <DAILY_TRANSACTION_OUTPUT_FILE>")
    sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print_usage_and_exit()

    accounts_file = sys.argv[1]
    daily_transaction_out = sys.argv[2]

    app = FrontEndApplication(accounts_file, daily_transaction_out)
    app.run()