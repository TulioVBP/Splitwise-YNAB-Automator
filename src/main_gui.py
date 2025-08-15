import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import os
import yaml
import pandas as pd
from splitwise_expenses import SplitwiseExpenses
from read_yaml_config import read_yaml_config
from get_latest_timestamp_for_user import get_latest_timestamp_for_user

class BudgetSimplifierGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Budget Simplifier")
        self.root.geometry("400x300")
        
        # Load config
        self.config_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config/config.yaml')
        self.config = read_yaml_config(self.config_file_path)
        self.output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
        
        self.setup_ui()
        
    def setup_ui(self):
        # Title
        title_label = tk.Label(self.root, text="Budget Simplifier", font=("Arial", 16, "bold"))
        title_label.pack(pady=20)
        
        # Current user display
        current_user = self.config['splitwise_api']['expenses']['user_name']
        user_label = tk.Label(self.root, text=f"Current User: {current_user}", font=("Arial", 12))
        user_label.pack(pady=10)
        
        # Buttons
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=20)
        
        btn_debts = tk.Button(btn_frame, text="Retrieve Latest Debts", 
                             command=self.retrieve_debts, width=20, height=2)
        btn_debts.pack(pady=5)
        
        btn_credits = tk.Button(btn_frame, text="Retrieve Latest Credits", 
                               command=self.retrieve_credits, width=20, height=2)
        btn_credits.pack(pady=5)
        
        btn_change_user = tk.Button(btn_frame, text="Change User Name", 
                                   command=self.change_user_name, width=20, height=2)
        btn_change_user.pack(pady=5)
        
        # Status label
        self.status_label = tk.Label(self.root, text="Ready", fg="green")
        self.status_label.pack(pady=20)
        
    def retrieve_debts(self):
        try:
            self.status_label.config(text="Retrieving debts...", fg="orange")
            self.root.update()
            
            user_name = self.config['splitwise_api']['expenses']['user_name']
            latest_file, latest_timestamp = get_latest_timestamp_for_user(self.output_dir, user_name)
            
            s = SplitwiseExpenses(self.config, latest_timestamp)
            s.create_ynab_expense_file_from_df(user_name)
            
            self.status_label.config(text="Debts retrieved successfully!", fg="green")
            messagebox.showinfo("Success", f"Debts for {user_name} have been retrieved and saved to output folder.")
            
        except Exception as e:
            self.status_label.config(text="Error retrieving debts", fg="red")
            messagebox.showerror("Error", f"Failed to retrieve debts: {str(e)}")
    
    def retrieve_credits(self):
        try:
            self.status_label.config(text="Retrieving credits...", fg="orange")
            self.root.update()
            
            user_name = self.config['splitwise_api']['expenses']['user_name']
            latest_file, latest_timestamp = get_latest_timestamp_for_user(self.output_dir, user_name)
            
            s = SplitwiseExpenses(self.config, latest_timestamp)
            df = s.get_expenses_dataframe()
            
            # Filter for credits (where user is the loaner)
            credits_df = df[df['Loaner'] == user_name]
            
            if not credits_df.empty:
                output_path = os.path.join(self.output_dir, f"credits_{user_name}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv")
                credits_df.to_csv(output_path, index=False)
                self.status_label.config(text="Credits retrieved successfully!", fg="green")
                messagebox.showinfo("Success", f"Credits for {user_name} have been retrieved and saved to output folder.")
            else:
                self.status_label.config(text="No credits found", fg="orange")
                messagebox.showinfo("Info", f"No credits found for {user_name}.")
                
        except Exception as e:
            self.status_label.config(text="Error retrieving credits", fg="red")
            messagebox.showerror("Error", f"Failed to retrieve credits: {str(e)}")
    
    def change_user_name(self):
        current_user = self.config['splitwise_api']['expenses']['user_name']
        new_user = simpledialog.askstring("Change User", f"Current user: {current_user}\nEnter new user name:")
        
        if new_user and new_user.strip():
            try:
                # Update config
                self.config['splitwise_api']['expenses']['user_name'] = new_user.strip()
                
                # Save to file
                with open(self.config_file_path, 'w') as file:
                    yaml.dump(self.config, file, default_flow_style=False)
                
                self.status_label.config(text="User name updated successfully!", fg="green")
                messagebox.showinfo("Success", f"User name changed to: {new_user.strip()}")
                
                # Refresh UI
                self.root.destroy()
                main()
                
            except Exception as e:
                self.status_label.config(text="Error updating user name", fg="red")
                messagebox.showerror("Error", f"Failed to update user name: {str(e)}")

def main():
    root = tk.Tk()
    app = BudgetSimplifierGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()